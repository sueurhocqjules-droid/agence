// Alarme hors de GitHub (sous-étape 17) : un Worker Cloudflare gratuit, indépendant de GitHub.
//
// Le réveil de l'agence envoie un signe de vie à chaque passage (POST /signe, secret partagé en
// « Authorization: Bearer »). Toutes les heures, le cron regarde depuis quand le dernier signe est
// arrivé : au-delà de DELAI_MINUTES, Jules reçoit un message Telegram, puis un rappel par délai de
// silence en plus. Au retour du premier signe après une alarme, Jules est prévenu que l'agence revit.
//
// Liaisons (posées par python -m agence.alarme deployer) : ETAT (KV), DELAI_MINUTES, ESSAI (« 1 » le
// temps d'un test : messages marqués TEST, pas de message de retour), secrets SIGNE_SECRET,
// TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID.
//
// Les décisions sont des fonctions pures (decider, apresSigne), testées par tests/test_alarme.py avec Node.

const CLE = "etat";
const ACTIONS = "https://github.com/sueurhocqjules-droid/agence/actions/workflows/reveil.yml";

export function decider(maintenant, etat, delaiMinutes) {
  // Renvoie null (rien à faire) ou {minutes} : l'agence est silencieuse depuis {minutes} et il faut prévenir
  if (!etat || !etat.dernier) return null;
  const delai = delaiMinutes * 60000;
  const silence = maintenant - Date.parse(etat.dernier);
  if (silence < delai) return null;
  if (etat.alerte && maintenant - Date.parse(etat.alerte) < delai) return null;  // un rappel par délai, pas plus
  return { minutes: Math.floor(silence / 60000) };
}

export function apresSigne(maintenant, etat, source) {
  // Nouvel état après un signe de vie, et s'il faut annoncer le retour (alarme réelle envoyée avant)
  const retour = Boolean(etat && etat.alerte && !etat.alerte_essai);
  return { etat: { dernier: new Date(maintenant).toISOString(), source, alerte: null, alerte_essai: false }, retour };
}

function duree(minutes) {
  if (minutes < 120) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h`;
}

function heureParis(iso) {
  return new Date(iso).toLocaleString("fr-FR", { timeZone: "Europe/Paris", dateStyle: "short", timeStyle: "short" });
}

export function messageAlarme(etat, minutes, essai) {
  const lignes = [];
  if (essai) lignes.push("[TEST de l'alarme, rien à faire]");
  lignes.push(`Alarme de l'agence : aucun signe de vie depuis ${duree(minutes)} (dernier : ${heureParis(etat.dernier)}, ${etat.source || "réveil"}).`);
  if (etat.source === "mise en service") {
    lignes.push("Aucun réveil n'a encore parlé à l'alarme : le secret ALARME_SECRET est-il posé sur GitHub ? (python -m agence.alarme poser-secret-github)");
  } else {
    lignes.push("Le réveil GitHub ne tourne plus, ou GitHub est en panne. Les derniers passages :");
  }
  lignes.push(ACTIONS);
  return lignes.join("\n");
}

async function egal(a, b) {
  // Comparaison à temps constant, sur les empreintes (longueurs égales)
  const enc = new TextEncoder();
  const [ha, hb] = await Promise.all([crypto.subtle.digest("SHA-256", enc.encode(a)), crypto.subtle.digest("SHA-256", enc.encode(b))]);
  return crypto.subtle.timingSafeEqual(ha, hb);
}

async function telegram(env, texte) {
  const reponse = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: Number(env.TELEGRAM_CHAT_ID), text: texte, disable_web_page_preview: true }),
  });
  const resultat = await reponse.json();
  if (!resultat.ok) throw new Error(`Telegram : ${resultat.description}`);
  return resultat.result.message_id;
}

async function lire(env) {
  return (await env.ETAT.get(CLE, "json")) || {};
}

export default {
  async fetch(requete, env) {
    const url = new URL(requete.url);
    if (requete.method !== "POST" || url.pathname !== "/signe") return new Response("", { status: 404 });
    const fourni = (requete.headers.get("Authorization") || "").replace(/^Bearer /, "");
    if (!fourni || !(await egal(fourni, env.SIGNE_SECRET))) return new Response("", { status: 401 });
    let source = "réveil";
    try {
      const corps = await requete.json();
      if (typeof corps.source === "string") source = corps.source.slice(0, 80);
    } catch (e) { /* corps vide : réveil */ }
    const { etat, retour } = apresSigne(Date.now(), await lire(env), source);
    await env.ETAT.put(CLE, JSON.stringify(etat));
    if (retour) await telegram(env, `L'agence redonne signe de vie (${source}, ${heureParis(etat.dernier)}). L'alarme est levée.`);
    return Response.json({ ok: true, dernier: etat.dernier });
  },

  async scheduled(evenement, env) {
    const etat = await lire(env);
    const essai = env.ESSAI === "1";
    const alarme = decider(evenement.scheduledTime, etat, Number(env.DELAI_MINUTES));
    if (!alarme) return;
    const message = await telegram(env, messageAlarme(etat, alarme.minutes, essai));
    etat.alerte = new Date(evenement.scheduledTime).toISOString();
    etat.alerte_essai = essai;
    etat.alerte_message = message;
    await env.ETAT.put(CLE, JSON.stringify(etat));
  },
};
