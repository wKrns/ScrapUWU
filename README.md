# 🕷️ ScraperUWU

ScraperUWU est un petit scraper web en Python.
Il prend une URL, parcourt les pages, extrait les infos avec des sélecteurs CSS, et enregistre le tout dans un dossier propre.


# 📦 Installation

Clone le projet et installe les dépendances :

git clone https://github.com/wKrns/scraperuwu.git

cd scraperuwu

pip install -r requirements.txt



# ⚙️ Fonctionnalités

🔎 Scrape en temps réel à partir d’une URL donnée (via argument ou input).

🌐 Crawl interne possible (reste dans le même domaine).

📄 Pagination auto (si bouton “Next”).

📝 Sauvegarde en JSONL ou CSV.

📂 Chaque site scrapé a son propre dossier de sortie (./output/example.com/).

🎲 Rotation aléatoire des User-Agents.

🔁 Retries & gestion du rate limit.

⏱️ Délai entre requêtes pour éviter de se faire bannir.


Les fichiers sont enregistrés dans :

./output/<domaine>/


# Exemple :

output/

 └── example.com/
 
     └── results.jsonl
     


# Discord : .krns 
feel free too add 
