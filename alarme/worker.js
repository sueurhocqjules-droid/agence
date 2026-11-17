// Alarme hors de GitHub (sous-étape 17) : un Worker Cloudflare gratuit, indépendant de GitHub.
//
// Le réveil de l'agence envoie un signe de vie à chaque passage (POST /signe, secret partagé en
// « Authorization: Bearer »). Toutes les heures, le cron regarde depuis quand le dernier signe est
// arrivé : au-delà de DELAI_MINUTES, Jules reçoit un message Telegram, puis un rappel par délai de
// silence en plus. Au retour du premier signe après une alarme, Jules est prévenu que l'agence revit.
//
// Il reçoit aussi les clics de Jules sur les boutons Oui/Non (demande #46). Telegram efface un clic non lu au
// bout de 2 à 3 minutes : le réveil, qui passe au mieux toutes les 6 h, ne les voyait jamais. Telegram les pousse
// donc ici (webhook POST /telegram, en-tête X-Telegram-Bot-Api-Secret-Token). Un clic de Jules est accusé, le
// message change aussitôt (boutons retirés), le clic est gardé dans le KV et le workflow reponses.yml est
// relancé pour l'appliquer. agence/questions.py lit les clics gardés (GET /clics) et les marque lus
// (POST /clics/lus), avec le secret du signe de vie.
//
// C'est aussi l'horloge du réveil. Le cron de GitHub sautait environ un créneau sur deux et retardait les autres
// de 1 h 30 à 4 h 30 (relevé du 11 au 17/11). Chaque heure, le cron du Worker regarde le dernier créneau passé
// (heures UTC choisies par l'agence dans organisation/rythme.toml, transmises à chaque signe de vie) : si aucun
// réveil programmé n'a donné signe de vie depuis, il lance reveil.yml (workflow_dispatch, programme=true).
// Le cron de GitHub reste un filet : reveil.yml ne fait rien s'il passe après un réveil récent.
//
// Liaisons (posées par python -m agence.alarme deployer) : ETAT (KV), DELAI_MINUTES, ESSAI (« 1 » le
// temps d'un test : messages marqués TEST, pas de message de retour, aucun réveil lancé), secrets SIGNE_SECRET,
// TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_SECRET et, s'il est posé, GITHUB_RELANCE_TOKEN (Actions en
// écriture sur agence seul ; sans lui, le clic s'applique au prochain réveil et le réveil dépend du cron de GitHub).
//
// Les décisions sont des fonctions pures (decider, apresSigne, reveilDu, lireClic, reponseClic, texteEnregistre),
// testées par tests/test_alarme.py avec Node, comme les routes (fetch, scheduled) sur un KV et un réseau simulés.

const CLE = "etat";
const DEPOT = "sueurhocqjules-droid/agence";
const ACTIONS = `https://github.com/${DEPOT}/actions/workflows/reveil.yml`;
const PREFIXE_CLIC = "clic:";
const GARDE_CLIC_S = 30 * 86400;   // un clic jamais lu disparaît seul au bout de 30 jours
const HEURES_PAR_DEFAUT = [5, 11, 17, 23];   // celles du cron de GitHub, tant que le réveil n'en a pas transmis d'autres
const NOUVEL_ESSAI_MS = 3 * 3600000;   // un réveil lancé resté sans signe de vie (file d'attente, panne) est relancé

export function decider(maintenant, etat, delaiMinutes) {
  // Renvoie null (rien à faire) ou {minutes} : l'agence est silencieuse depuis {minutes} et il faut prévenir
  if (!etat || !etat.dernier) return null;
  const delai = delaiMinutes * 60000;
  const silence = maintenant - Date.parse(etat.dernier);
  if (silence < delai) return null;
  if (etat.alerte && maintenant - Date.parse(etat.alerte) < delai) return null;  // un rappel par délai, pas plus
  return { minutes: Math.floor(silence / 60000) };
}

export function apresSigne(maintenant, etat, source, heures) {
  // Nouvel état après un signe de vie, et s'il faut annoncer le retour (alarme réelle envoyée avant).
  // Seul un réveil programmé (source « réveil ») compte pour son créneau ; les heures transmises remplacent les anciennes.
  const avant = etat || {};
  const retour = Boolean(avant.alerte && !avant.alerte_essai);
  const quand = new Date(maintenant).toISOString();
  const suite = { dernier: quand, source, alerte: null, alerte_essai: false };
  const reveil = source === "réveil" ? quand : dernierReveil(avant);
  if (reveil) suite.reveil = reveil;
  if (avant.relance_reveil) suite.relance_reveil = avant.relance_reveil;
  if (heures !== undefined) suite.heures = heuresValides(heures);
  else if (avant.heures) suite.heures = avant.heures;
  return { etat: suite, retour };
}

function dernierReveil(etat) {
  // Avant la mise en place de « reveil », le dernier signe venait d'un réveil quand sa source le disait
  return etat.reveil || (etat.source === "réveil" ? etat.dernier : null);
}

export function heuresValides(heures) {
  if (!Array.isArray(heures) || !heures.length || heures.length > 24) return HEURES_PAR_DEFAUT;
  if (!heures.every((h) => Number.isInteger(h) && h >= 0 && h <= 23)) return HEURES_PAR_DEFAUT;
  return [...new Set(heures)].sort((a, b) => a - b);
}

export function dernierCreneau(maintenant, heures) {
  // Le dernier créneau commencé (heure UTC pile), aujourd'hui ou hier, en millisecondes
  const minuit = maintenant - (maintenant % 86400000);
  const candidats = [0, 1].flatMap((j) => heures.map((h) => minuit - j * 86400000 + h * 3600000));
  return Math.max(...candidats.filter((t) => t <= maintenant));
}

export function reveilDu(maintenant, etat) {
  // L'heure (ISO) du créneau dont le réveil reste à lancer, ou null : déjà passé, ou lancé il y a moins de 3 h
  const e = etat || {};
  const creneau = dernierCreneau(maintenant, heuresValides(e.heures));
  const reveil = dernierReveil(e);
  if (reveil && Date.parse(reveil) >= creneau) return null;
  const relance = e.relance_reveil ? Date.parse(e.relance_reveil) : 0;
  if (relance >= creneau && maintenant - relance < NOUVEL_ESSAI_MS) return null;
  return new Date(creneau).toISOString();
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

// --- Clics de Jules ------------------------------------------------------------------------------------------

export function lireClic(update, chat) {
  // Le clic utile d'une update Telegram, ou null s'il ne vient pas de la conversation de Jules
  const c = update && update.callback_query;
  if (!c || !c.from || c.from.id !== chat || !c.message || !c.message.chat || c.message.chat.id !== chat) return null;
  if (!Number.isSafeInteger(update.update_id)) return null;
  return {
    update_id: update.update_id,
    clic_id: String(c.id),
    donnee: String(c.data || "").slice(0, 64),
    message_id: c.message.message_id,
    envoi: c.message.date || 0,
    texte: String(c.message.text || "").slice(0, 3500),
  };
}

export function reponseClic(donnee) {
  // « oui » ou « non » pour un bouton de question (même forme que CLIC dans agence/questions.py), sinon null
  const trouve = /^q:[0-9a-z-]{1,24}:(oui|non)$/.exec(donnee);
  return trouve ? trouve[1] : null;
}

export function texteEnregistre(texte, reponse, relance) {
  const quand = relance ? "Appliquée dans les minutes qui viennent" : "Appliquée au prochain réveil de l'agence";
  return `${texte ? `${texte}\n\n` : ""}Décision enregistrée : ${reponse.toUpperCase()}. ${quand}, ce message le dira.`;
}

function cleClic(id) {
  return `${PREFIXE_CLIC}${String(id).padStart(12, "0")}`;   // ordre des clés = ordre des clics
}

async function appelTelegram(env, methode, donnees) {
  // Un échec ici ne perd pas le clic (déjà gardé) : il est noté, jamais levé
  try {
    const reponse = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${methode}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(donnees),
    });
    const resultat = await reponse.json();
    if (!resultat.ok) console.log(`Telegram ${methode} : ${resultat.description}`);
  } catch (e) {
    console.log(`Telegram ${methode} injoignable : ${e}`);
  }
}

async function relancer(env, workflow, entrees) {
  // Lance un workflow tout de suite (workflow_dispatch) : reponses.yml après un clic, reveil.yml à son créneau.
  // Rend true si GitHub l'a accepté. Ne lève jamais.
  try {
    const reponse = await fetch(`https://api.github.com/repos/${DEPOT}/actions/workflows/${workflow}/dispatches`, {
      method: "POST",
      headers: { Authorization: `Bearer ${env.GITHUB_RELANCE_TOKEN}`, Accept: "application/vnd.github+json",
                 "User-Agent": "agence-alarme", "X-GitHub-Api-Version": "2022-11-28" },
      body: JSON.stringify(entrees ? { ref: "main", inputs: entrees } : { ref: "main" }),
    });
    if (!reponse.ok) console.log(`Relance de ${workflow} refusée : ${reponse.status}`);
    return reponse.ok;
  } catch (e) {
    console.log(`GitHub injoignable : ${e}`);
    return false;
  }
}

async function webhook(requete, env, ctx) {
  const fourni = requete.headers.get("X-Telegram-Bot-Api-Secret-Token") || "";
  if (!env.WEBHOOK_SECRET || !fourni || !(await egal(fourni, env.WEBHOOK_SECRET))) return new Response("", { status: 401 });
  let update;
  try {
    update = await requete.json();
  } catch (e) {
    return new Response("");   // illisible : rien à garder, et Telegram ne le renvoie pas
  }
  const clic = lireClic(update, Number(env.TELEGRAM_CHAT_ID));
  if (!clic) return new Response("");
  // Gardé d'abord : si le KV échoue, la réponse 500 fait renvoyer le clic par Telegram
  await env.ETAT.put(cleClic(clic.update_id), JSON.stringify({ ...clic, recu: new Date().toISOString() }),
                     { expirationTtl: GARDE_CLIC_S });
  const reponse = reponseClic(clic.donnee);
  const relance = Boolean(env.GITHUB_RELANCE_TOKEN);
  await appelTelegram(env, "answerCallbackQuery", { callback_query_id: clic.clic_id, text: reponse ? `Bien reçu : ${reponse}` : "Bien reçu" });
  if (reponse) {
    await appelTelegram(env, "editMessageText", { chat_id: Number(env.TELEGRAM_CHAT_ID), message_id: clic.message_id,
                                                  text: texteEnregistre(clic.texte, reponse, relance).slice(0, 4096),
                                                  disable_web_page_preview: true });
  }
  if (relance) ctx.waitUntil(relancer(env, "reponses.yml"));
  return new Response("");
}

async function clicsGardes(env) {
  const clics = [];
  let curseur;
  do {
    const page = await env.ETAT.list({ prefix: PREFIXE_CLIC, cursor: curseur });
    for (const cle of page.keys) {
      const clic = await env.ETAT.get(cle.name, "json");
      if (clic) clics.push(clic);
    }
    curseur = page.list_complete ? undefined : page.cursor;
  } while (curseur);
  return clics;
}

async function marquerLus(requete, env) {
  let ids = [];
  try {
    ids = (await requete.json()).ids;
  } catch (e) { /* corps illisible : rien à marquer */ }
  if (!Array.isArray(ids) || !ids.every(Number.isSafeInteger)) return new Response("", { status: 400 });
  await Promise.all(ids.map((id) => env.ETAT.delete(cleClic(id))));
  return Response.json({ ok: true, lus: ids.length });
}

async function autorise(requete, env) {
  const fourni = (requete.headers.get("Authorization") || "").replace(/^Bearer /, "");
  return Boolean(fourni) && (await egal(fourni, env.SIGNE_SECRET));
}

export default {
  async fetch(requete, env, ctx) {
    const url = new URL(requete.url);
    const route = `${requete.method} ${url.pathname}`;
    if (route === "POST /telegram") return webhook(requete, env, ctx);
    if (!["POST /signe", "GET /clics", "POST /clics/lus"].includes(route)) return new Response("", { status: 404 });
    if (!(await autorise(requete, env))) return new Response("", { status: 401 });
    if (route === "GET /clics") return Response.json({ clics: await clicsGardes(env) });
    if (route === "POST /clics/lus") return marquerLus(requete, env);
    let source = "réveil";
    let heures;
    try {
      const corps = await requete.json();
      if (typeof corps.source === "string") source = corps.source.slice(0, 80);
      if (corps.heures_utc !== undefined) heures = corps.heures_utc;
    } catch (e) { /* corps vide : réveil */ }
    const { etat, retour } = apresSigne(Date.now(), await lire(env), source, heures);
    await env.ETAT.put(CLE, JSON.stringify(etat));
    if (retour) await telegram(env, `L'agence redonne signe de vie (${source}, ${heureParis(etat.dernier)}). L'alarme est levée.`);
    return Response.json({ ok: true, dernier: etat.dernier });
  },

  async scheduled(evenement, env) {
    const etat = await lire(env);
    const essai = env.ESSAI === "1";
    const t = evenement.scheduledTime;
    let change = false;
    // L'horloge du réveil : pas en essai (cron chaque minute), pas avant la mise en service, pas sans jeton
    if (!essai && etat.dernier && env.GITHUB_RELANCE_TOKEN && reveilDu(t, etat)) {
      if (await relancer(env, "reveil.yml", { programme: "true" })) {
        etat.relance_reveil = new Date(t).toISOString();
        change = true;
      }
    }
    const alarme = decider(t, etat, Number(env.DELAI_MINUTES));
    if (alarme) {
      etat.alerte_message = await telegram(env, messageAlarme(etat, alarme.minutes, essai));
      etat.alerte = new Date(t).toISOString();
      etat.alerte_essai = essai;
      change = true;
    }
    if (change) await env.ETAT.put(CLE, JSON.stringify(etat));
  },
};
