import React from "react";
import { Composition } from "remotion";
import { BibleShort } from "./BibleShort";
import { DevotionalSample } from "./DevotionalSample";
import { SAMPLE } from "./sampleData";
import { DEVOTIONAL } from "./devotionalSampleData";

const FPS = 30;
export const DURATION = Math.ceil((SAMPLE.duration + 1.2) * FPS);
export const DEVOTIONAL_DURATION = Math.ceil((DEVOTIONAL.duration + 1.2) * FPS);

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="BibleShort"
        component={BibleShort}
        durationInFrames={DURATION}
        fps={FPS}
        width={1080}
        height={1920}
        defaultProps={{
          verseData: SAMPLE,
          backgroundImage: null,
        }}
      />
      <Composition
        id="DevotionalSample"
        component={DevotionalSample}
        durationInFrames={DEVOTIONAL_DURATION}
        fps={FPS}
        width={1080}
        height={1920}
      />
    </>
  );
};
