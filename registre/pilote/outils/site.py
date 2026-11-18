"""Site vitrine des affiches Every Second : une page par affiche, un flux RSS pour l'import automatique de Pinterest.

Usage : python3 registre/pilote/outils/site.py <url de base> <dossier des affiches 4K> <dossier de sortie>
  <url de base>       : https://<projet>.pages.dev (Cloudflare Pages, envoi du dossier à la main par Jules)
  <dossier affiches>  : <sujet>-en.jpg (rendus par chaines-studio/scripts/affiches.py)
Lit : chaines-studio/sujets/<sujet>.json et .calcul.json (titres, descriptions, sources), registre/stats.csv (vidéo
YouTube publique du même titre, intégrée à la page), organisation/diffusion.toml [boutique] lien (bouton Ko-fi).
Sans réseau, sans secret.
"""
import csv
import html
import json
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
STUDIO = RACINE / "chaines-studio"
CHAINE = "https://www.youtube.com/channel/UCiuTySJ8_2u6VEuJSM7ED8Q"
LARGEUR_WEB = 1000

STYLE = """body{margin:0;background:#111;color:#f4efe6;font-family:system-ui,sans-serif;line-height:1.5}
main{max-width:1100px;margin:auto;padding:24px}h1{font-size:2rem;margin:.2em 0}a{color:#ffc94d}
.grille{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}
.grille a{color:#f4efe6;text-decoration:none;font-size:.9rem}.grille img,.affiche{width:100%;height:auto;border-radius:4px}
.bouton{display:inline-block;background:#ffc94d;color:#111;padding:12px 20px;border-radius:6px;font-weight:700;
text-decoration:none;margin:8px 8px 8px 0}.video{aspect-ratio:9/16;width:min(360px,100%);border:0}
.deux{display:grid;grid-template-columns:2fr 1fr;gap:24px}@media(max-width:800px){.deux{grid-template-columns:1fr}}"""


def boutique():
    with open(RACINE / "organisation" / "diffusion.toml", "rb") as f:
        return (tomllib.load(f).get("boutique") or {}).get("lien", "").strip()


def videos_publiques():
    """Titre exact -> identifiant de la vidéo YouTube anglaise publique (dernier relevé)."""
    vues = {}
    with open(RACINE / "registre" / "stats.csv", encoding="utf-8") as f:
        for ligne in csv.DictReader(f):
            if ligne["chaine"] == "en" and ligne["statut"] == "public":
                vues[ligne["titre"]] = ligne["video_id"]
    return vues


def fiche(nom):
    sujet = json.loads((STUDIO / "sujets" / f"{nom}.json").read_text(encoding="utf-8"))
    calcul = json.loads((STUDIO / "sujets" / f"{nom}.calcul.json").read_text(encoding="utf-8"))
    texte = calcul["descriptions"]["en"].split("\n")
    sources = next((l for l in texte if l.startswith("Sources")), "")
    return {"nom": nom, "titre": sujet["en"]["titre"], "resume": texte[0], "sources": sources}


def page(contenu, titre, description, base, chemin):
    t, d = html.escape(titre), html.escape(description)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{t}</title>'
            f'<meta name="description" content="{d}"><link rel="canonical" href="{base}{chemin}">'
            f'<link rel="alternate" type="application/rss+xml" href="{base}/rss.xml">'
            f'<meta property="og:title" content="{t}"><meta property="og:description" content="{d}">'
            f"<style>{STYLE}</style></head><body><main>{contenu}"
            f'<footer><p><a href="/">Every Second posters</a> · <a href="{CHAINE}">YouTube</a></p></footer>'
            f"</main></body></html>")


def boutons(lien):
    achat = f'<a class="bouton" href="{html.escape(lien)}">Get the 4K printable posters</a>' if lien else ""
    return achat + f'<a class="bouton" href="{CHAINE}">Watch the Shorts</a>'


def construire(base, affiches, sortie, maintenant=None):
    base = base.rstrip("/")
    maintenant = maintenant or datetime.now(timezone.utc)
    lien, videos = boutique(), videos_publiques()
    noms = sorted(p.name[:-len("-en.jpg")] for p in Path(affiches).glob("*-en.jpg"))
    (sortie / "p").mkdir(parents=True, exist_ok=True)
    (sortie / "img").mkdir(exist_ok=True)
    fiches, items = [], []
    for nom in noms:
        f = fiche(nom)
        fiches.append(f)
        image = sortie / "img" / f"{nom}.jpg"
        if not image.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(Path(affiches) / f"{nom}-en.jpg"),
                            "-vf", f"scale={LARGEUR_WEB}:-1", "-q:v", "4", str(image)], check=True)
        video = videos.get(f["titre"])
        lecteur = (f'<iframe class="video" src="https://www.youtube-nocookie.com/embed/{video}" title="{html.escape(f["titre"])}" '
                   f'allowfullscreen loading="lazy"></iframe>') if video else ""
        contenu = (f'<h1>{html.escape(f["titre"])}</h1><div class="deux"><div><img class="affiche" '
                   f'src="/img/{nom}.jpg" alt="{html.escape(f["titre"])} science infographic poster" width="1000" '
                   f'height="1432"></div><div><p>{html.escape(f["resume"])}</p><p>Every number is computed, '
                   f'nothing is written by hand. {html.escape(f["sources"])}</p>{boutons(lien)}{lecteur}</div></div>')
        (sortie / "p" / f"{nom}.html").write_text(page(contenu, f"{f['titre']} – Science Poster", f["resume"], base,
                                                       f"/p/{nom}.html"), encoding="utf-8")
        items.append(f)
    grille = "".join(f'<a href="/p/{f["nom"]}.html"><img src="/img/{f["nom"]}.jpg" alt="{html.escape(f["titre"])}" '
                     f'loading="lazy" width="1000" height="1432">{html.escape(f["titre"])}</a>' for f in fiches)
    accueil = ("<h1>Every Second – science posters</h1><p>One absurd rule, applied every second, with real numbers "
               f"and sources. Each poster shows six moments of one of our science Shorts.</p>{boutons(lien)}"
               f'<div class="grille">{grille}</div>')
    (sortie / "index.html").write_text(page(accueil, "Every Second – science posters",
                                            "Science infographic posters: one absurd rule applied every second, "
                                            "real math and sources.", base, "/"), encoding="utf-8")
    date = format_datetime(maintenant)
    rss = "".join(f"<item><title>{html.escape(f['titre'])}</title><link>{base}/p/{f['nom']}.html</link>"
                  f"<guid>{base}/p/{f['nom']}.html</guid><description>{html.escape(f['resume'])}</description>"
                  f'<enclosure url="{base}/img/{f["nom"]}.jpg" type="image/jpeg" length="0"/>'
                  f"<pubDate>{date}</pubDate></item>" for f in items)
    (sortie / "rss.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Every Second – science posters'
        f"</title><link>{base}/</link><description>Science infographic posters from the Every Second Shorts."
        f"</description>{rss}</channel></rss>", encoding="utf-8")
    (sortie / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    plan = "".join(f"<url><loc>{base}/p/{f['nom']}.html</loc></url>" for f in fiches)
    (sortie / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{base}/</loc></url>{plan}</urlset>", encoding="utf-8")
    return len(fiches)


if __name__ == "__main__":
    print(construire(sys.argv[1], sys.argv[2], Path(sys.argv[3])), "pages")
