"""Agent stats : relève vues, likes et commentaires de chaque vidéo des chaînes, dans registre/stats.csv.

Lancement : python -m agents.stats [en es pt]
Script pur, aucun modèle : 0 jeton. Quota YouTube : environ 3 unités par chaîne.
"""
import sys

from agence import registre, youtube


def relever(langues):
    lignes, releve = [], registre.maintenant()
    for langue in langues:
        for v in youtube.videos(youtube.client(langue)):
            s, st = v.get("statistics", {}), v["status"]
            lignes.append({
                "releve": releve, "chaine": langue, "video_id": v["id"], "titre": v["snippet"]["title"],
                # une vidéo rejetée (droits d'auteur, règles...) est notée pour la Sûreté, qui met la chaîne en pause
                "statut": st["privacyStatus"] if st.get("uploadStatus") != "rejected"
                          else f"rejete:{st.get('rejectionReason', 'inconnu')}",
                "sortie": st.get("publishAt") or v["snippet"]["publishedAt"],
                "vues": s.get("viewCount", 0), "likes": s.get("likeCount", 0), "commentaires": s.get("commentCount", 0),
            })
    registre.ajouter("stats", lignes)
    return lignes


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    langues = sys.argv[1:] or list(youtube.CHAINES)
    with registre.seance("stats") as info:
        lignes = relever(langues)
        vues = sum(int(l["vues"]) for l in lignes)
        info["resultat"] = f"ok : {len(lignes)} vidéos, {vues} vues"
        print(info["resultat"])


if __name__ == "__main__":
    main()
