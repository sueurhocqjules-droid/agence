import React from "react";
import {AbsoluteFill, Audio, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";

export type Indice = {icone: string; texte: string};
export type GuessTheProductDonnees = {categorie: string; produit: string; indices: Indice[]; voix?: string};

// Chronologie en secondes : 3 indices de 5 s, compte à rebours de 3 s, puis la révélation de 6 s.
export const SECONDES_PAR_INDICE = 5;
export const SECONDES_COMPTE_A_REBOURS = 3;
export const SECONDES_REVELATION = 6;
export const SECONDES_TOTAL = 3 * SECONDES_PAR_INDICE + SECONDES_COMPTE_A_REBOURS + SECONDES_REVELATION;

export const GuessTheProduct: React.FC<GuessTheProductDonnees> = ({categorie, produit, indices, voix}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const finIndices = indices.length * SECONDES_PAR_INDICE;
  const finCompte = finIndices + SECONDES_COMPTE_A_REBOURS;
  const revele = t >= finCompte;
  const chiffre = Math.max(1, Math.ceil(finCompte - t));
  const entreeRevelation = spring({frame: frame - Math.round(finCompte * fps), fps, config: {damping: 10}});

  return (
    <AbsoluteFill style={{backgroundColor: "#12122a", fontFamily: "sans-serif", color: "white"}}>
      {voix ? <Audio src={staticFile(voix)} /> : null}
      <div style={{position: "absolute", top: 110, width: "100%", textAlign: "center", fontSize: 64, fontWeight: 800, color: "#f4d03f"}}>
        GUESS THE PRODUCT
      </div>
      <div style={{position: "absolute", top: 200, width: "100%", textAlign: "center", fontSize: 48, opacity: 0.8}}>{categorie}</div>
      {!revele && indices.map((ind, i) => {
        const debut = i * SECONDES_PAR_INDICE * fps;
        if (frame < debut) return null;
        const entree = spring({frame: frame - debut, fps, config: {damping: 14}});
        return (
          <div key={i} style={{position: "absolute", left: 80, right: 80, top: 360 + i * 330, height: 280, borderRadius: 40,
            backgroundColor: "#1f2a5a", display: "flex", alignItems: "center", gap: 40, padding: "0 50px",
            transform: `scale(${interpolate(entree, [0, 1], [0.6, 1])})`, opacity: Math.min(1, entree)}}>
            <span style={{fontSize: 130}}>{ind.icone}</span>
            <span style={{fontSize: 56, fontWeight: 700}}>{ind.texte}</span>
          </div>
        );
      })}
      {t >= finIndices && !revele ? (
        <div style={{position: "absolute", bottom: 120, width: "100%", textAlign: "center", fontSize: 260, fontWeight: 900, color: "#e74c3c"}}>
          {chiffre}
        </div>
      ) : null}
      {revele ? (
        <div style={{position: "absolute", top: 640, width: "100%", textAlign: "center",
          transform: `scale(${interpolate(entreeRevelation, [0, 1], [0.3, 1])})`}}>
          <div style={{fontSize: 70, opacity: 0.8}}>It's...</div>
          <div style={{fontSize: 130, fontWeight: 900, color: "#58d68d", padding: "0 60px"}}>{produit}</div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
