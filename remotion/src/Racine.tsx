import React from "react";
import {Composition} from "remotion";
import {ScaleZoom, ScaleZoomDonnees} from "./ScaleZoom";
import {OneSecVsOneHour, OneSecVsOneHourDonnees} from "./OneSecVsOneHour";
import exempleZoom from "../exemples/scale-zoom.json";
import exempleTemps from "../exemples/one-sec-vs-one-hour.json";

// 9:16, 30 s à 30 images par seconde
export const LARGEUR = 1080;
export const HAUTEUR = 1920;
export const FPS = 30;
export const DUREE = 30 * FPS;

export const Racine: React.FC = () => (
  <>
    <Composition id="ScaleZoom" component={ScaleZoom} width={LARGEUR} height={HAUTEUR} fps={FPS}
      durationInFrames={DUREE} defaultProps={exempleZoom as ScaleZoomDonnees} />
    <Composition id="OneSecVsOneHour" component={OneSecVsOneHour} width={LARGEUR} height={HAUTEUR} fps={FPS}
      durationInFrames={DUREE} defaultProps={exempleTemps as OneSecVsOneHourDonnees} />
  </>
);
