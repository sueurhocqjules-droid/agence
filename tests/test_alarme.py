"""Alarme hors de GitHub (sous-étape 17) : le signe de vie du réveil et les décisions du Worker.

python -m unittest discover tests
"""
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from agence import alarme

RACINE = Path(__file__).resolve().parent.parent
HEURE = 3_600_000


class Reponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Signe(unittest.TestCase):
    def test_sans_secret_rien_ne_part(self):
        appels = []
        with mock.patch.dict(os.environ, {"ALARME_SECRET": ""}):
            self.assertFalse(alarme.signe(ouvrir=lambda *a, **k: appels.append(a)))
        self.assertEqual(appels, [])

    def test_le_secret_part_dans_l_en_tete_jamais_dans_l_adresse(self):
        vues = []

        def ouvrir(requete, timeout):
            vues.append(requete)
            return Reponse(b'{"ok": true, "dernier": "2026-11-14T00:00:00Z"}')

        with mock.patch.dict(os.environ, {"ALARME_SECRET": "s3cret"}):
            self.assertTrue(alarme.signe(ouvrir=ouvrir))
        requete = vues[0]
        self.assertEqual(requete.get_method(), "POST")
        self.assertEqual(requete.get_header("Authorization"), "Bearer s3cret")
        self.assertNotIn("s3cret", requete.full_url)
        self.assertEqual(requete.full_url, alarme.ADRESSE)

    def test_un_refus_ou_une_panne_ne_casse_jamais_le_reveil(self):
        def refus(requete, timeout):
            raise urllib.error.HTTPError(requete.full_url, 401, "non", {}, None)

        def panne(requete, timeout):
            raise urllib.error.URLError("injoignable")

        with mock.patch.dict(os.environ, {"ALARME_SECRET": "s3cret"}):
            self.assertFalse(alarme.signe(ouvrir=refus))
            self.assertFalse(alarme.signe(ouvrir=panne))

    def test_le_reveil_envoie_le_signe_meme_si_un_agent_a_echoue(self):
        texte = (RACINE / ".github/workflows/reveil.yml").read_text(encoding="utf-8")
        etape = texte.split("- name: Signe de vie")[1]
        self.assertIn("if: always()", etape)
        self.assertIn("python -m agence.alarme signe", etape)
        self.assertIn("ALARME_SECRET: ${{ secrets.ALARME_SECRET }}", etape)

    def test_le_signe_transmet_les_heures_du_reveil(self):
        vues = []

        def ouvrir(requete, timeout):
            vues.append(json.loads(requete.data))
            return Reponse(b'{"ok": true}')

        with mock.patch.dict(os.environ, {"ALARME_SECRET": "s3cret"}):
            alarme.signe(ouvrir=ouvrir, heures=[5, 17])
            alarme.signe("réveil à la main", ouvrir=ouvrir)
        self.assertEqual(vues[0], {"source": "réveil", "heures_utc": [5, 17]})
        self.assertEqual(vues[1]["source"], "réveil à la main")
        self.assertEqual(vues[1]["heures_utc"], alarme.heures_reveil())

    def test_heures_du_reveil_lues_dans_le_rythme_et_verifiees(self):
        self.assertTrue(alarme.heures_reveil())   # organisation/rythme.toml en donne
        with tempfile.TemporaryDirectory() as d:
            fichier = Path(d, "rythme.toml")
            for texte, attendu in (("[reveil]\nheures_utc = [17, 5, 5]", [5, 17]),
                                   ("[reveil]\nheures_utc = [5, 24]", None),
                                   ("[reveil]\nheures_utc = []", None),
                                   ("[reveil]\nheures_utc = [true]", None),
                                   ("[direction]\nseances_par_jour = 1", None),
                                   ("pas du toml [", None)):
                fichier.write_text(texte, encoding="utf-8")
                self.assertEqual(alarme.heures_reveil(fichier), attendu, texte)
        self.assertIsNone(alarme.heures_reveil(Path("absent.toml")))

    def test_seul_un_reveil_programme_compte_pour_son_creneau(self):
        texte = (RACINE / ".github/workflows/reveil.yml").read_text(encoding="utf-8")
        self.assertIn("type: boolean", texte.split("programme:")[1].split("jobs:")[0])
        seance = texte.split("- name: Séance du Pilote")[1].split("- name:")[0]
        self.assertIn("github.event_name == 'schedule' || inputs.programme", seance)
        self.assertIn("gh run list -w pilote.yml", seance)   # une séance au plus par créneau
        etape = texte.split("- name: Signe de vie")[1]
        self.assertIn("'réveil' || 'réveil à la main'", etape)
        self.assertIn('signe "$SOURCE"', etape)

    def test_le_cron_de_github_n_est_qu_un_filet(self):
        texte = (RACINE / ".github/workflows/reveil.yml").read_text(encoding="utf-8")
        garde = texte.split("  garde:")[1].split("  agents:")[0]
        self.assertIn("-e workflow_dispatch", garde)
        self.assertIn("5 hours ago", garde)
        agents = texte.split("  agents:")[1].split("steps:")[0]
        self.assertIn("needs: garde", agents)
        self.assertIn("needs.garde.outputs.lancer == 'true'", agents)


class Deploiement(unittest.TestCase):
    def test_liaisons_du_worker(self):
        meta = alarme.metadonnees("kv", alarme.DELAI_MINUTES, False, "s", "b", "c")
        liaisons = {l["name"]: l for l in meta["bindings"]}
        self.assertEqual(liaisons["DELAI_MINUTES"]["text"], "1440")
        self.assertEqual(liaisons["ESSAI"]["text"], "")
        for nom in ("SIGNE_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            self.assertEqual(liaisons[nom]["type"], "secret_text")   # jamais en clair dans le tableau de bord
        self.assertEqual(liaisons["ETAT"]["type"], "kv_namespace")
        self.assertEqual(alarme.metadonnees("kv", 2, True, "s", "b", "c")["bindings"][2]["text"], "1")

    def test_le_delai_normal_couvre_les_retards_connus_de_github(self):
        self.assertGreaterEqual(alarme.DELAI_MINUTES, 19 * 60)   # un créneau sauté et un autre retardé de 7 h (11/11)
        self.assertEqual(alarme.CRON, "7 * * * *")

    def test_le_secret_partage_n_est_jamais_suivi_par_git(self):
        self.assertIn(".secrets/", (RACINE / ".gitignore").read_text(encoding="utf-8").splitlines())

    def test_liaisons_des_clics(self):
        liaisons = {l["name"]: l for l in alarme.metadonnees("kv", 1440, False, "s", "b", "c", "w", "")["bindings"]}
        self.assertEqual(liaisons["WEBHOOK_SECRET"]["type"], "secret_text")
        self.assertNotIn("GITHUB_RELANCE_TOKEN", liaisons)   # pas de jeton : pas de liaison vide
        avec = {l["name"]: l for l in alarme.metadonnees("kv", 1440, False, "s", "b", "c", "w", "r")["bindings"]}
        self.assertEqual(avec["GITHUB_RELANCE_TOKEN"]["type"], "secret_text")


class ClicsDuWorker(unittest.TestCase):
    """Côté Python : lecture des clics gardés par le Worker (demande #46)."""

    def test_lecture_avec_le_secret_en_en_tete_et_dans_l_ordre(self):
        vues = []

        def ouvrir(requete, timeout):
            vues.append(requete)
            return Reponse(json.dumps({"clics": [{"update_id": 9}, {"update_id": 3}]}).encode())

        with mock.patch.dict(os.environ, {"ALARME_SECRET": "s3cret"}):
            self.assertEqual([c["update_id"] for c in alarme.clics_recus(ouvrir=ouvrir)], [3, 9])
        self.assertEqual(vues[0].get_header("Authorization"), "Bearer s3cret")
        self.assertEqual(vues[0].full_url, f"{alarme.BASE}/clics")
        self.assertNotIn("s3cret", vues[0].full_url)

    def test_un_refus_du_worker_fait_echouer_la_releve(self):
        def refus(requete, timeout):
            raise urllib.error.HTTPError(requete.full_url, 401, "non", {}, None)

        with mock.patch.dict(os.environ, {"ALARME_SECRET": "s3cret"}), self.assertRaises(RuntimeError):
            alarme.clics_recus(ouvrir=refus)

    def test_les_deux_workflows_lisent_les_clics(self):
        for nom in ("reveil.yml", "reponses.yml"):
            texte = (RACINE / ".github/workflows" / nom).read_text(encoding="utf-8")
            etape = texte.split("- name: Réponses de Jules")[1].split("- name:")[0]
            self.assertIn("ALARME_SECRET: ${{ secrets.ALARME_SECRET }}", etape)
            self.assertIn("python -m agence.lancer reponses relever", etape)

    def test_une_relance_n_annule_jamais_un_reveil_en_attente(self):
        texte = (RACINE / ".github/workflows/reponses.yml").read_text(encoding="utf-8")
        self.assertIn("group: reponses", texte)
        self.assertNotIn("group: registre", texte)


@unittest.skipUnless(shutil.which("node"), "Node absent")
class RoutesDuWorker(unittest.TestCase):
    """Les routes de alarme/worker.js sur un KV et un réseau simulés : Telegram et GitHub ne sont jamais appelés."""

    HARNAIS = """
crypto.subtle.timingSafeEqual ??= (a, b) => {
  const x = new Uint8Array(a), y = new Uint8Array(b);
  let d = x.length ^ y.length;
  for (let i = 0; i < Math.min(x.length, y.length); i++) d |= x[i] ^ y[i];
  return d === 0;
};
const { default: w } = await import(__SOURCE__);
const kv = new Map();
const ETAT = {
  async get(k, type) { const v = kv.get(k); return v === undefined ? null : (type === "json" ? JSON.parse(v) : v); },
  async put(k, v) { kv.set(k, v); },
  async delete(k) { kv.delete(k); },
  async list({ prefix }) { return { keys: [...kv.keys()].filter((k) => k.startsWith(prefix)).sort().map((name) => ({ name })), list_complete: true }; },
};
const appels = [];
globalThis.fetch = async (url, init) => {
  appels.push({ url: String(url).replace(/bot[^/]+\\//, "bot***/"), corps: init && init.body ? JSON.parse(init.body) : null });
  return new Response(JSON.stringify({ ok: true, result: true }), { status: 200 });
};
const attente = [];
const ctx = { waitUntil: (p) => attente.push(p) };
const env = { ETAT, SIGNE_SECRET: "signe", WEBHOOK_SECRET: "crochet", TELEGRAM_BOT_TOKEN: "jeton-bot", TELEGRAM_CHAT_ID: "77",
              GITHUB_RELANCE_TOKEN: __RELANCE__ };
async function appel(methode, chemin, corps, entetes) {
  const r = await w.fetch(new Request("https://alarme.test" + chemin, { method: methode, headers: entetes || {},
                                      body: corps === undefined ? undefined : JSON.stringify(corps) }), env, ctx);
  await Promise.all(attente);
  const texte = await r.text();
  return { statut: r.status, corps: texte ? JSON.parse(texte) : null };
}
const clic = (chat, id) => ({ update_id: id, callback_query: { id: "cb" + id, from: { id: chat }, data: "q:1117-0047-1:oui",
                              message: { message_id: 5, date: 1, chat: { id: chat }, text: "Je fusionne la PR #99 ?" } } });
const S = { "X-Telegram-Bot-Api-Secret-Token": "crochet" };
const B = { Authorization: "Bearer signe" };
"""

    def scenario(self, code, relance=""):
        harnais = self.HARNAIS.replace("__SOURCE__", json.dumps((RACINE / "alarme/worker.js").as_uri())) \
                              .replace("__RELANCE__", json.dumps(relance))
        programme = f"{harnais}\nconst resultat = await (async () => {{ {code} }})();\n" \
                    "console.log(JSON.stringify({ resultat, appels, cles: [...kv.keys()] }));"
        sortie = subprocess.run(["node", "--input-type=module", "-e", programme], capture_output=True, text=True,
                                encoding="utf-8", check=True)
        return json.loads(sortie.stdout)

    def test_webhook_refuse_sans_le_secret(self):
        r = self.scenario("return [(await appel('POST', '/telegram', clic(77, 1))).statut, "
                          "(await appel('POST', '/telegram', clic(77, 1), { 'X-Telegram-Bot-Api-Secret-Token': 'faux' })).statut, "
                          "(await appel('POST', '/telegram', clic(77, 1), B)).statut];")
        self.assertEqual(r["resultat"], [401, 401, 401])
        self.assertEqual((r["cles"], r["appels"]), ([], []))

    def test_clic_d_une_autre_conversation_ignore(self):
        r = self.scenario("return (await appel('POST', '/telegram', clic(99, 1), S)).statut;")
        self.assertEqual(r["resultat"], 200)   # 200 : Telegram ne le renvoie pas
        self.assertEqual((r["cles"], r["appels"]), ([], []))

    def test_clic_de_jules_garde_accuse_et_message_change(self):
        r = self.scenario("await appel('POST', '/telegram', clic(77, 600000001), S); "
                          "return (await appel('POST', '/telegram', clic(77, 600000001), S)).statut;")   # renvoyé deux fois
        self.assertEqual(r["resultat"], 200)
        self.assertEqual(r["cles"], ["clic:000600000001"])
        methodes = [a["url"].rsplit("/", 1)[1] for a in r["appels"]]
        self.assertEqual(methodes[:2], ["answerCallbackQuery", "editMessageText"])
        self.assertNotIn("jeton-bot", json.dumps(r["appels"]))
        edition = r["appels"][1]["corps"]
        self.assertEqual((edition["chat_id"], edition["message_id"]), (77, 5))
        self.assertIn("Je fusionne la PR #99 ?\n\nDécision enregistrée : OUI. Appliquée au prochain réveil", edition["text"])
        self.assertNotIn("reply_markup", edition)   # boutons retirés
        self.assertFalse(any("api.github.com" in a["url"] for a in r["appels"]))   # pas de jeton : pas de relance

    def test_avec_le_jeton_le_workflow_reponses_est_relance(self):
        r = self.scenario("return (await appel('POST', '/telegram', clic(77, 600000001), S)).statut;", relance="jeton-gh")
        relances = [a for a in r["appels"] if "api.github.com" in a["url"]]
        self.assertEqual(len(relances), 1)
        self.assertTrue(relances[0]["url"].endswith("/repos/sueurhocqjules-droid/agence/actions/workflows/reponses.yml/dispatches"))
        self.assertEqual(relances[0]["corps"], {"ref": "main"})
        self.assertIn("dans les minutes qui viennent", r["appels"][1]["corps"]["text"])

    def test_clics_lus_avec_le_secret_seulement_puis_retires(self):
        r = self.scenario("""
          await appel('POST', '/telegram', clic(77, 600000002), S);
          await appel('POST', '/telegram', clic(77, 600000001), S);
          const sans = (await appel('GET', '/clics')).statut;
          const faux = (await appel('GET', '/clics', undefined, S)).statut;
          const lus = (await appel('GET', '/clics', undefined, B)).corps.clics.map((c) => [c.update_id, c.donnee, c.message_id]);
          const mauvais = (await appel('POST', '/clics/lus', { ids: ['clic:x'] }, B)).statut;
          const marque = (await appel('POST', '/clics/lus', { ids: [600000001] }, B)).corps;
          return { sans, faux, lus, mauvais, marque };""")
        self.assertEqual((r["resultat"]["sans"], r["resultat"]["faux"]), (401, 401))
        self.assertEqual(r["resultat"]["lus"], [[600000001, "q:1117-0047-1:oui", 5], [600000002, "q:1117-0047-1:oui", 5]])
        self.assertEqual(r["resultat"]["mauvais"], 400)
        self.assertEqual(r["resultat"]["marque"], {"ok": True, "lus": 1})
        self.assertEqual(r["cles"], ["clic:000600000002"])

    def test_le_worker_lance_le_reveil_a_son_heure_une_fois(self):
        r = self.scenario("""
          env.DELAI_MINUTES = "1440";
          kv.set("etat", JSON.stringify({ dernier: "2026-11-17T11:20:00Z", source: "réveil", heures: [5, 11, 17, 23] }));
          await w.scheduled({ scheduledTime: Date.parse("2026-11-17T16:07:00Z") }, env);   // créneau de 11 h fait
          await w.scheduled({ scheduledTime: Date.parse("2026-11-17T17:07:00Z") }, env);   // créneau de 17 h : relance
          await w.scheduled({ scheduledTime: Date.parse("2026-11-17T18:07:00Z") }, env);   // déjà relancé
          return JSON.parse(kv.get("etat"));""", relance="jeton-gh")
        relances = [a for a in r["appels"] if "api.github.com" in a["url"]]
        self.assertEqual(len(relances), 1)
        self.assertTrue(relances[0]["url"].endswith("/actions/workflows/reveil.yml/dispatches"))
        self.assertEqual(relances[0]["corps"], {"ref": "main", "inputs": {"programme": "true"}})
        self.assertEqual(r["resultat"]["relance_reveil"], "2026-11-17T17:07:00.000Z")
        self.assertFalse(any("telegram" in a["url"] for a in r["appels"]))   # aucune alarme

    def test_sans_jeton_ni_signe_aucun_reveil_lance(self):
        r = self.scenario("""
          env.DELAI_MINUTES = "1440";
          await w.scheduled({ scheduledTime: Date.parse("2026-11-17T17:07:00Z") }, env);   // jamais de signe
          kv.set("etat", JSON.stringify({ dernier: "2026-11-17T05:20:00Z", source: "réveil" }));
          env.GITHUB_RELANCE_TOKEN = "";
          await w.scheduled({ scheduledTime: Date.parse("2026-11-17T17:07:00Z") }, env);
          env.GITHUB_RELANCE_TOKEN = "jeton-gh"; env.ESSAI = "1";
          await w.scheduled({ scheduledTime: Date.parse("2026-11-17T17:07:00Z") }, env);
          return 0;""", relance="jeton-gh")
        self.assertFalse(any("api.github.com" in a["url"] for a in r["appels"]))

    def test_le_signe_garde_le_reveil_et_les_heures(self):
        r = self.scenario("""
          await appel('POST', '/signe', { source: 'réveil', heures_utc: [6, 18] }, B);
          const reveil = JSON.parse(kv.get("etat"));
          await appel('POST', '/signe', { source: 'réveil à la main' }, B);
          return { reveil, main: JSON.parse(kv.get("etat")) };""")
        reveil, main = r["resultat"]["reveil"], r["resultat"]["main"]
        self.assertEqual(reveil["heures"], [6, 18])
        self.assertEqual(reveil["reveil"], reveil["dernier"])
        self.assertEqual((main["reveil"], main["heures"], main["source"]), (reveil["reveil"], [6, 18], "réveil à la main"))

    def test_le_signe_de_vie_marche_toujours(self):
        r = self.scenario("return (await appel('POST', '/signe', { source: 'essai' }, B)).corps.ok;")
        self.assertTrue(r["resultat"])

    def test_bouton_qui_n_est_pas_une_question(self):
        self.assertIsNone(Worker.js(self, "w.reponseClic('q:../x:oui')"))
        self.assertEqual(Worker.js(self, "w.reponseClic('q:1117-0047-1:non')"), "non")


@unittest.skipUnless(shutil.which("node"), "Node absent")
class Worker(unittest.TestCase):
    """Les fonctions pures de alarme/worker.js, exécutées par Node."""

    def js(self, expression):
        source = (RACINE / "alarme/worker.js").as_uri()
        code = f"import * as w from '{source}'; console.log(JSON.stringify({expression}));"
        sortie = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True)
        return json.loads(sortie.stdout)

    def test_silence_court_rien(self):
        self.assertIsNone(self.js(f"w.decider(Date.parse('2026-11-14T10:00:00Z'), "
                                  f"{{dernier: '2026-11-14T00:00:00Z'}}, 1440)"))

    def test_silence_long_alarme(self):
        self.assertEqual(self.js(f"w.decider(Date.parse('2026-11-15T01:00:00Z'), "
                                 f"{{dernier: '2026-11-14T00:00:00Z'}}, 1440)"), {"minutes": 25 * 60})

    def test_un_rappel_par_delai_pas_plus(self):
        etat = "{dernier: '2026-11-14T00:00:00Z', alerte: '2026-11-15T00:07:00Z'}"
        self.assertIsNone(self.js(f"w.decider(Date.parse('2026-11-15T05:07:00Z'), {etat}, 1440)"))
        self.assertIsNotNone(self.js(f"w.decider(Date.parse('2026-11-16T00:07:00Z'), {etat}, 1440)"))

    def test_jamais_de_signe_rien(self):
        self.assertIsNone(self.js("w.decider(Date.now(), {}, 1440)"))

    def test_le_retour_n_est_annonce_qu_apres_une_vraie_alarme(self):
        vraie = self.js("w.apresSigne(0, {dernier: 'x', alerte: '2026-11-14T00:00:00Z', alerte_essai: false}, 'réveil')")
        essai = self.js("w.apresSigne(0, {dernier: 'x', alerte: '2026-11-14T00:00:00Z', alerte_essai: true}, 'réveil')")
        calme = self.js("w.apresSigne(0, {dernier: 'x', alerte: null}, 'réveil')")
        self.assertEqual([vraie["retour"], essai["retour"], calme["retour"]], [True, False, False])
        self.assertIsNone(vraie["etat"]["alerte"])

    def test_reveil_du_au_dernier_creneau_passe(self):
        def du(maintenant, etat):
            return self.js(f"w.reveilDu(Date.parse('{maintenant}'), {etat})")
        self.assertIsNone(du("2026-11-17T16:07:00Z", "{reveil: '2026-11-17T11:30:00Z'}"))
        self.assertEqual(du("2026-11-17T17:07:00Z", "{reveil: '2026-11-17T11:30:00Z'}"), "2026-11-17T17:00:00.000Z")
        # minuit passé : le créneau de 23 h de la veille
        self.assertEqual(du("2026-11-18T02:07:00Z", "{reveil: '2026-11-17T17:30:00Z'}"), "2026-11-17T23:00:00.000Z")
        # heures choisies par l'agence
        self.assertIsNone(du("2026-11-17T16:07:00Z", "{reveil: '2026-11-17T11:30:00Z', heures: [11, 20]}"))
        self.assertEqual(du("2026-11-17T20:07:00Z", "{reveil: '2026-11-17T11:30:00Z', heures: [11, 20]}"),
                         "2026-11-17T20:00:00.000Z")
        # ancien état : le dernier signe compte s'il venait d'un réveil
        self.assertIsNone(du("2026-11-17T12:07:00Z", "{dernier: '2026-11-17T11:30:00Z', source: 'réveil'}"))
        self.assertIsNotNone(du("2026-11-17T12:07:00Z", "{dernier: '2026-11-17T11:30:00Z', source: 'réveil à la main'}"))

    def test_un_reveil_lance_sans_nouvelles_est_relance_au_bout_de_3_h(self):
        etat = "{reveil: '2026-11-17T11:30:00Z', relance_reveil: '2026-11-17T17:07:00Z'}"
        self.assertIsNone(self.js(f"w.reveilDu(Date.parse('2026-11-17T19:07:00Z'), {etat})"))
        self.assertEqual(self.js(f"w.reveilDu(Date.parse('2026-11-17T20:07:00Z'), {etat})"), "2026-11-17T17:00:00.000Z")

    def test_heures_invalides_remplacees_par_celles_du_cron(self):
        for mauvaises in ("[]", "[24]", "[1.5]", "'5'", "null", "[-1]"):
            self.assertEqual(self.js(f"w.heuresValides({mauvaises})"), [5, 11, 17, 23], mauvaises)
        self.assertEqual(self.js("w.heuresValides([17, 5, 5])"), [5, 17])

    def test_apres_signe_seul_le_reveil_programme_avance(self):
        avant = ("{dernier: 'x', source: 'réveil', reveil: '2026-11-17T05:20:00Z', "
                 "relance_reveil: '2026-11-17T05:07:00Z', heures: [5, 17]}")
        main = self.js(f"w.apresSigne(Date.parse('2026-11-17T09:00:00Z'), {avant}, 'réveil à la main')")["etat"]
        self.assertEqual((main["reveil"], main["relance_reveil"], main["heures"]),
                         ("2026-11-17T05:20:00Z", "2026-11-17T05:07:00Z", [5, 17]))
        prog = self.js(f"w.apresSigne(Date.parse('2026-11-17T17:20:00Z'), {avant}, 'réveil', [6])")["etat"]
        self.assertEqual((prog["reveil"], prog["heures"]), ("2026-11-17T17:20:00.000Z", [6]))

    def test_messages(self):
        essai = self.js("w.messageAlarme({dernier: '2026-11-14T00:00:00Z', source: 'réveil'}, 1500, true)")
        self.assertTrue(essai.startswith("[TEST"))
        self.assertIn("25 h", essai)
        service = self.js("w.messageAlarme({dernier: '2026-11-14T00:00:00Z', source: 'mise en service'}, 1500, false)")
        self.assertIn("ALARME_SECRET", service)
        self.assertNotIn("TEST", service)


if __name__ == "__main__":
    unittest.main()
