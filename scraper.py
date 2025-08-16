import re
import csv
import os
import time
import json
import random
import argparse
import urllib.parse as up
from collections import deque
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/125.0",
]

def build_session(timeout=20, proxies_env=True):
    s = requests.Session()
    s.headers.update({"Accept-Language": "en,fr;q=0.8"})
    s.timeout = timeout
    if proxies_env:
        # Respecte les variables d’env proxy si présentes
        s.trust_env = True
    return s

def get(url, session, max_retries=3, backoff=1.5, timeout=20):
    last_err = None
    for i in range(max_retries):
        try:
            session.headers["User-Agent"] = random.choice(USER_AGENTS)
            r = session.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code in (429, 503):
                # backoff sur rate limit
                time.sleep(backoff ** (i + 1) + random.random())
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            time.sleep(backoff ** (i + 1) + random.random())
    raise last_err

def same_domain(seed, url):
    a = up.urlparse(seed)
    b = up.urlparse(url)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)

def normalize_url(base, href):
    if not href:
        return None
    href = href.strip()
    # ignore anchors/mailto/tel/javascript
    if href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    return up.urljoin(base, href)

def extract_with_selectors(soup, selectors):
    """selectors: dict {field: {"css": ".class", "attr": "href" | None, "all": bool}}"""
    data = {}
    for field, rule in selectors.items():
        css = rule.get("css")
        attr = rule.get("attr")
        all_flag = rule.get("all", False)
        if not css:
            data[field] = None
            continue
        nodes = soup.select(css)
        if not nodes:
            data[field] = [] if all_flag else None
            continue
        if all_flag:
            vals = []
            for n in nodes:
                vals.append(n.get(attr).strip() if attr else n.get_text(strip=True))
            data[field] = vals
        else:
            n = nodes[0]
            data[field] = n.get(attr).strip() if attr else n.get_text(strip=True)
    return data

def save_jsonl(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def save_csv(rows, path):
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    fields = sorted({k for row in rows for k in row.keys()})
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def scrape_seed(seed_url, selectors, session, crawl=False, link_css="a", link_pattern=None,
                max_pages=50, delay=0.8, follow_pagination_css=None):
    """
    - seed_url: page de départ
    - selectors: dict de sélecteurs CSS pour extraire des champs
    - crawl: True => explore les liens internes (même domaine)
    - link_css: sélecteur CSS des liens à suivre (si crawl=True)
    - link_pattern: regex pour filtrer les liens (ex: r"/product/\\d+")
    - follow_pagination_css: sélecteur pour le bouton/lien 'Next' (pagination)
    """
    seen = set()
    queue = deque([seed_url])
    out = []

    pbar = tqdm(total=max_pages, desc="Pages")
    while queue and len(seen) < max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        try:
            r = get(url, session)
        except Exception as e:
            tqdm.write(f"[warn] {url} -> {e}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")  # parser intégré à Python
        row = {"url": url}
        row.update(extract_with_selectors(soup, selectors))
        out.append(row)
        pbar.update(1)

        # Pagination (ex: bouton "Next")
        if follow_pagination_css:
            nxt = soup.select_one(follow_pagination_css)
            if nxt and nxt.get("href"):
                nxt_url = normalize_url(url, nxt.get("href"))
                if nxt_url and nxt_url not in seen:
                    queue.append(nxt_url)

        # Crawl interne
        if crawl:
            for a in soup.select(link_css):
                href = normalize_url(url, a.get("href"))
                if not href:
                    continue
                if not same_domain(seed_url, href):
                    continue
                if link_pattern and not re.search(link_pattern, href):
                    continue
                if href not in seen:
                    queue.append(href)

        time.sleep(delay + random.random() * 0.3)

    pbar.close()
    return out

def main():
    ap = argparse.ArgumentParser(description="Scraper mais pas envie d’expliquer")
    ap.add_argument("url", nargs="?", help="url de départ (seed)")
    ap.add_argument("--selectors", type=str, default=None,
                    help="json inline ou fichier (flemme de détailler)")
    ap.add_argument("--crawl", action="store_true", help="crawl same domain si t’insistes")
    ap.add_argument("--link-css", default="a", help="css pour links, bref")
    ap.add_argument("--link-pattern", default=None, help="regex pour filtrer")
    ap.add_argument("--pagination-css", default=None, help="next button osef")
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--delay", type=float, default=0.8, help="sleep sinon ban")
    ap.add_argument("--out", default=None, help="sortie (.jsonl ou .csv)")
    args = ap.parse_args()

    # si pas d’URL en argument → demande à l’utilisateur
    if not args.url:
        args.url = input("👉 Entre l’URL Tocard W3B : ").strip()

    # charge sélecteurs par défaut
    if not args.selectors:
        selectors = {
            "title": {"css": "title"},
            "h1": {"css": "h1"},
            "links_on_page": {"css": "a", "attr": "href", "all": True}
        }
    else:
        if os.path.exists(args.selectors):
            selectors = json.loads(Path(args.selectors).read_text(encoding="utf-8"))
        else:
            selectors = json.loads(args.selectors)

    session = build_session()

    rows = scrape_seed(
        seed_url=args.url,
        selectors=selectors,
        session=session,
        crawl=args.crawl,
        link_css=args.link_css,
        link_pattern=args.link_pattern,
        max_pages=args.max_pages,
        delay=args.delay,
        follow_pagination_css=args.pagination_css
    )

    # crée dossier de sortie basé sur domaine
    domain = up.urlparse(args.url).netloc.replace(":", "_")
    out_dir = Path("output") / domain
    out_dir.mkdir(parents=True, exist_ok=True)

    # fichier de sortie (par défaut JSONL)
    if args.out:
        out_file = Path(args.out)
    else:
        out_file = out_dir / "results.jsonl"

    if out_file.suffix.lower() == ".csv":
        save_csv(rows, out_file)
    else:
        save_jsonl(rows, out_file)

    print(f"✅ fini. {len(rows)} pages scrapées → {out_file}")

if __name__ == "__main__":
    main()
    try:
        print("🟢 Scraper fini. CTRL+C pour quitter.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Bye.")
