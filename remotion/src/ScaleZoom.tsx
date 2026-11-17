import React from "react";
import {AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame, useVideoConfig} from "remotion";

export type ObjetEchelle = {nom: string; taille_m: number; couleur: string};
export type ScaleZoomDonnees = {titre: string; objets: ObjetEchelle[]; voix?: string};

const nombre = (v: number): string => v.toLocaleString("fr-FR", {maximumSignificantDigits: 3});

const formater = (m: number): string => {
  if (m >= 1000) return `${nombre(m / 1000)} km`;
  if (m >= 1) return `${nombre(m)} m`;
  if (m >= 0.001) return `${nombre(m * 1000)} mm`;
  if (m >= 1e-6) return `${nombre(m * 1e6)} µm`;
  return `${nombre(m * 1e9)} nm`;
};

// Zoom continu : on parcourt l'échelle en logarithme, du plus petit au plus grand objet.
export const ScaleZoom: React.FC<ScaleZoomDonnees> = ({titre, objets, voix}) => {
  const frame = useCurrentFrame();
  const {durationInFrames, height} = useVideoConfig();
  const tries = [...objets].sort((a, b) => a.taille_m - b.taille_m);
  const logs = tries.map((o) => Math.log10(o.taille_m));
  const logActuel = interpolate(frame, [0, durationInFrames - 1], [logs[0], logs[logs.length - 1]]);
  const reference = 500; // diamètre en pixels d'un objet à la taille indiquée par le compteur

  return (
    <AbsoluteFill style={{backgroundColor: "#0b0b14", fontFamily: "sans-serif", color: "white"}}>
      {voix ? <Audio src={staticFile(voix)} /> : null}
      <div style={{position: "absolute", top: 120, width: "100%", textAlign: "center", fontSize: 72, fontWeight: 700}}>{titre}</div>
      {tries.map((o, i) => {
        const diametre = reference * Math.pow(10, logs[i] - logActuel);
        if (diametre < 8 || diametre > height * 3) return null;
        const opacite = interpolate(diametre, [8, 40, reference * 4, reference * 8], [0, 1, 1, 0],
          {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
        return (
          <div key={o.nom} style={{position: "absolute", left: "50%", top: "50%", width: diametre, height: diametre,
            marginLeft: -diametre / 2, marginTop: -diametre / 2, borderRadius: "50%", backgroundColor: o.couleur,
            opacity: opacite * 0.85, display: "flex", alignItems: "flex-start", justifyContent: "center"}}>
            <span style={{fontSize: 56, fontWeight: 700, marginTop: Math.min(diametre / 2 - 30, 24)}}>{o.nom}</span>
          </div>
        );
      })}
      <div style={{position: "absolute", bottom: 160, width: "100%", textAlign: "center", fontSize: 110, fontWeight: 800}}>
        {formater(Math.pow(10, logActuel))}
      </div>
    </AbsoluteFill>
  );
};
