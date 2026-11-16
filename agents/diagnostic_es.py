"""Diagnostic de la chaîne es : compare ses réglages YouTube à ceux de pt (chaîne qui est diffusée) et corrige es.

Lancement : python -m agents.diagnostic_es            (lecture seule : écrit les écarts, ne change rien)
            python -m agents.diagnostic_es corriger   (met es comme pt, pour ce que l'API permet)
Script pur, aucun modèle. Reprend la demande #33 (PR #42, fermée en conflit).

Ce qui est comparé : public enfants, langue par défaut, pays, statut et visibilité des vidéos, restrictions
(régions, âge), catégorie, licence. La visibilité d'une vidéo (privée, programmée) est un état, pas un réglage :
elle est signalée mais jamais changée par ce script.
"""
import sys

from agence import youtube

REFERENCE, CIBLE = "pt", "es"
# champs de vidéo corrigeables : (partie, champ). La licence, le public enfants et la catégorie sont des réglages.
CORRIGEABLES = [("snippet", "categoryId"), ("snippet", "defaultLanguage"), ("status", "license"),
                ("status", "selfDeclaredMadeForKids"), ("status", "embeddable")]
# le reste de `status` en lecture seule : à retirer avant une mise à jour
LECTURE_SEULE = ("uploadStatus", "failureReason", "rejectionReason", "madeForKids")


def reglages_chaine(yt):
    """Réglages de la chaîne connectée : public enfants, langue par défaut, pays."""
    item = yt.channels().list(part="snippet,status,brandingSettings", mine=True).execute()["items"][0]
    canal = item.get("brandingSettings", {}).get("channel", {})
    return {
        "public_enfants": item.get("status", {}).get("madeForKids"),
        "declare_enfants": item.get("status", {}).get("selfDeclaredMadeForKids"),
        "langue_par_defaut": canal.get("defaultLanguage") or item.get("snippet", {}).get("defaultLanguage"),
        "pays": canal.get("country") or item.get("snippet", {}).get("country"),
    }


def reglages_video(v):
    """Réglages d'une vidéo, à plat."""
    sn, st, ct = v.get("snippet", {}), v.get("status", {}), v.get("contentDetails", {})
    restriction = ct.get("regionRestriction") or {}
    return {
        "visibilite": st.get("privacyStatus"),
        "statut_envoi": st.get("uploadStatus"),
        "rejet": st.get("rejectionReason"),
        "public_enfants": st.get("madeForKids"),
        "declare_enfants": st.get("selfDeclaredMadeForKids"),
        "langue_par_defaut": sn.get("defaultLanguage"),
        "langue_audio": sn.get("defaultAudioLanguage"),
        "categorie": sn.get("categoryId"),
        "licence": st.get("license"),
        "integrable": st.get("embeddable"),
        "regions_autorisees": ",".join(sorted(restriction.get("allowed", []))) or None,
        "regions_bloquees": ",".join(sorted(restriction.get("blocked", []))) or None,
        "limite_age": (ct.get("contentRating") or {}).get("ytRating"),
    }


def releve(langue):
    yt = youtube.client(langue)
    videos = youtube.videos(yt, "snippet,status,contentDetails")
    return {"chaine": reglages_chaine(yt), "videos": [reglages_video(v) for v in videos], "brut": videos, "yt": yt}


def resume_videos(videos):
    """Pour chaque réglage, le décompte des valeurs sur les vidéos de la chaîne."""
    resume = {}
    for v in videos:
        for champ, valeur in v.items():
            resume.setdefault(champ, {})
            resume[champ][valeur] = resume[champ].get(valeur, 0) + 1
    return resume


def valeur_courante(decompte):
    """La valeur la plus fréquente (None comprise)."""
    return max(decompte.items(), key=lambda kv: kv[1])[0] if decompte else None


def ecarts(es, pt):
    """Liste des écarts {portee, champ, es, pt}. Pour les vidéos, on compare la valeur la plus fréquente
    et on garde le décompte complet de es quand il n'est pas uniforme."""
    sortie = []
    for champ in sorted(set(es["chaine"]) | set(pt["chaine"])):
        if es["chaine"].get(champ) != pt["chaine"].get(champ):
            sortie.append({"portee": "chaine", "champ": champ, "es": es["chaine"].get(champ), "pt": pt["chaine"].get(champ)})
    r_es, r_pt = resume_videos(es["videos"]), resume_videos(pt["videos"])
    for champ in sorted(set(r_es) | set(r_pt)):
        a, b = valeur_courante(r_es.get(champ)), valeur_courante(r_pt.get(champ))
        if a != b or len(r_es.get(champ, {})) > 1:
            sortie.append({"portee": "videos", "champ": champ, "es": r_es.get(champ, {}), "pt": r_pt.get(champ, {}),
                           "reference": b})
    return sortie


def corriger_video(yt, video, reference):
    """Met une vidéo de es aux réglages de référence. `reference` : {(partie, champ): valeur}. Renvoie les champs changés."""
    corps = {"id": video["id"], "snippet": dict(video["snippet"]),
             "status": {k: v for k, v in video["status"].items() if k not in LECTURE_SEULE}}
    changes = []
    for partie, champ in CORRIGEABLES:
        if (partie, champ) not in reference:
            continue
        voulu = reference[(partie, champ)]
        if voulu is not None and corps[partie].get(champ) != voulu:
            corps[partie][champ] = voulu
            changes.append(champ)
    if changes:
        yt.videos().update(part="snippet,status", body=corps).execute()
    return changes


def reference_videos(pt):
    """Valeur la plus fréquente de pt pour chaque réglage corrigeable."""
    nom = {"categoryId": "categorie", "defaultLanguage": "langue_par_defaut", "license": "licence",
           "selfDeclaredMadeForKids": "declare_enfants", "embeddable": "integrable"}
    resume = resume_videos(pt["videos"])
    return {(p, c): valeur_courante(resume.get(nom[c])) for p, c in CORRIGEABLES}


def corriger(es, pt):
    """Corrige les vidéos de es. Les réglages de la chaîne elle-même (pays, langue, public enfants) se changent
    dans YouTube Studio ou demandent le droit complet « youtube », que les jetons n'ont pas : ils restent dans le
    rapport. Renvoie {video_id: champs changés}."""
    reference = reference_videos(pt)
    faits = {}
    for video in es["brut"]:
        changes = corriger_video(es["yt"], video, reference)
        if changes:
            faits[video["id"]] = changes
    return faits


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    es, pt = releve(CIBLE), releve(REFERENCE)
    liste = ecarts(es, pt)
    print(f"Écarts entre {CIBLE} ({len(es['videos'])} vidéos) et {REFERENCE} ({len(pt['videos'])} vidéos) : {len(liste)}")
    for e in liste:
        print(f"- {e['portee']} / {e['champ']} : {CIBLE}={e['es']}  {REFERENCE}={e['pt']}")
    if "corriger" in sys.argv[1:]:
        try:
            faits = corriger(es, pt)
        except Exception as erreur:  # le plus probable : jeton sans le droit d'écriture
            print(f"Correction impossible : {erreur}")
            return 1
        print(f"Vidéos corrigées : {len(faits)}")
        for vid, champs in faits.items():
            print(f"- {vid} : {', '.join(champs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
