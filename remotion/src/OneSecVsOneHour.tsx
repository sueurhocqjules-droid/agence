import React from "react";
import {AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig} from "remotion";

export type EtatTemps = {instant: number; seconde: string; heure: string; couleur: string};
export type OneSecVsOneHourDonnees = {titre: string; etats: EtatTemps[]; voix?: string};

const Ecran: React.FC<{libelle: string; texte: string; couleur: string}> = ({libelle, texte, couleur}) => (
  <div style={{flex: 1, backgroundColor: couleur, display: "flex", flexDirection: "column", alignItems: "center",
    justifyContent: "center", padding: 60, textAlign: "center"}}>
    <div style={{fontSize: 110, fontWeight: 800}}>{libelle}</div>
    <div style={{fontSize: 64, marginTop: 30}}>{texte}</div>
  </div>
);

// Deux écrans (1 s en haut, 1 h en bas), une barre de temps au milieu, des états qui se suivent.
export const OneSecVsOneHour: React.FC<OneSecVsOneHourDonnees> = ({titre, etats, voix}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const avancement = frame / (durationInFrames - 1);
  const tries = [...etats].sort((a, b) => a.instant - b.instant);
  const actuel = [...tries].reverse().find((e) => e.instant <= avancement) ?? tries[0];

  return (
    <AbsoluteFill style={{backgroundColor: "#000", fontFamily: "sans-serif", color: "white"}}>
      {voix ? <Audio src={staticFile(voix)} /> : null}
      <div style={{position: "absolute", top: 40, width: "100%", textAlign: "center", fontSize: 56, fontWeight: 700, zIndex: 2}}>{titre}</div>
      <div style={{display: "flex", flexDirection: "column", width: "100%", height: "100%"}}>
        <Ecran libelle="1 s" texte={actuel.seconde} couleur={actuel.couleur} />
        <div style={{height: 36, backgroundColor: "#222"}}>
          <div style={{height: "100%", width: `${avancement * 100}%`, backgroundColor: "white"}} />
        </div>
        <Ecran libelle="1 h" texte={actuel.heure} couleur={actuel.couleur} />
      </div>
    </AbsoluteFill>
  );
};
