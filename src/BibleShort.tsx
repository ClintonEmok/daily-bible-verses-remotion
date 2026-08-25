import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Easing,
} from "remotion";
import { SAMPLE } from "./sampleData";

type Phrase = {
  index: number;
  text: string;
  start: number;
  end: number;
};

type VerseData = {
  reference: string;
  verseText: string;
  phrases: Phrase[];
  audio: string;
  duration: number;
  voice: string;
  mode: string;
  alignment: string;
};

type BibleShortProps = {
  verseData?: VerseData;
  backgroundImage?: string | null;
};

const CANVAS = "#0B1120";
const INK = "#F8FAFC";
const MUTED = "rgba(226,232,240,0.36)";
const GOLD = "#E8C47A";
const HAIRLINE = "rgba(232,196,122,0.28)";

export const BibleShort: React.FC<BibleShortProps> = ({ verseData, backgroundImage }) => {
  const data = verseData ?? SAMPLE;
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const seconds = frame / fps;

  // Ken Burns: subtle zoom from 1.06 to 1.14 over the video duration
  const bgScale = interpolate(frame, [0, durationInFrames], [1.06, 1.14], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Header entrance animation
  const headerSpring = spring({
    frame,
    fps,
    config: { damping: 16, mass: 0.6, stiffness: 90 },
  });
  const headerY = interpolate(headerSpring, [0, 1], [36, 0]);
  const headerOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  // Find the currently active phrase based on playback time
  const activeIndex = data.phrases.findIndex((phrase, index) => {
    const nextStart = data.phrases[index + 1]?.start ?? phrase.end;
    return seconds >= phrase.start && seconds < nextStart;
  });

  // Fade out at end
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 18, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // Background layer: either an image with Ken Burns or a CSS gradient
  const bgLayer = backgroundImage ? (
    <AbsoluteFill
      style={{
        transform: `scale(${bgScale})`,
        overflow: "hidden",
      }}
    >
      <Img
        src={staticFile(backgroundImage)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          filter: "brightness(0.55) contrast(0.95)",
        }}
      />
    </AbsoluteFill>
  ) : (
    <AbsoluteFill
      style={{
        transform: `scale(${bgScale})`,
        background:
          "radial-gradient(120% 80% at 50% 0%, rgba(56,74,110,0.45) 0%, rgba(11,17,32,0) 60%), radial-gradient(100% 70% at 50% 100%, rgba(120,86,42,0.35) 0%, rgba(11,17,32,0) 55%), linear-gradient(180deg, #0D1526 0%, #0B1120 100%)",
      }}
    />
  );

  return (
    <AbsoluteFill style={{ backgroundColor: CANVAS, opacity: fadeOut }}>
      {/* Background with Ken Burns zoom */}
      {bgLayer}

      {/* Dark overlay for readability */}
      {backgroundImage && (
        <AbsoluteFill
          style={{
            background:
              "radial-gradient(120% 80% at 50% 30%, rgba(11,17,32,0.3) 0%, rgba(11,17,32,0.7) 100%)",
          }}
        />
      )}

      {/* Border frame */}
      <div
        style={{
          position: "absolute",
          inset: 48,
          border: `2px solid ${HAIRLINE}`,
          borderRadius: 8,
        }}
      />

      {/* Header: reference + translation */}
      <div
        style={{
          position: "absolute",
          top: 142,
          width: "100%",
          textAlign: "center",
          opacity: headerOpacity,
          transform: `translateY(${headerY}px)`,
        }}
      >
        <div
          style={{
            fontSize: 46,
            fontWeight: 700,
            letterSpacing: 14,
            color: GOLD,
            fontFamily: "Georgia, serif",
          }}
        >
          {data.reference}
        </div>
        <div
          style={{
            marginTop: 22,
            fontSize: 28,
            letterSpacing: 5,
            color: "rgba(226,232,240,0.58)",
            fontFamily: "Arial, sans-serif",
            textTransform: "uppercase",
          }}
        >
          King James Version
        </div>
      </div>

      {/* Phrase captions with active highlighting */}
      <div
        style={{
          position: "absolute",
          top: 340,
          left: 82,
          right: 82,
          display: "flex",
          flexDirection: "column",
          gap: 22,
        }}
      >
        {data.phrases.map((phrase, index) => {
          const isActive = index === activeIndex;
          const isSpoken =
            activeIndex > index || (activeIndex < 0 && seconds > phrase.end);
          const color = isActive ? GOLD : isSpoken ? INK : MUTED;
          const opacity = isActive || isSpoken ? 1 : 0.9;
          const scale = isActive ? 1.015 : 1;

          return (
            <div
              key={phrase.index}
              style={{
                color,
                opacity,
                fontSize: 70,
                fontWeight: isActive ? 700 : 600,
                lineHeight: 1.22,
                fontFamily: "Georgia, 'Times New Roman', serif",
                transform: `scale(${scale})`,
                transformOrigin: "center left",
                textShadow: isActive
                  ? "0 0 34px rgba(232,196,122,0.28)"
                  : "none",
              }}
            >
              {phrase.text}
            </div>
          );
        })}
      </div>

      {/* Footer branding */}
      <div
        style={{
          position: "absolute",
          bottom: 148,
          left: 82,
          right: 82,
          display: "flex",
          alignItems: "center",
          gap: 22,
        }}
      >
        <div style={{ width: 94, height: 3, background: GOLD }} />
        <div
          style={{
            fontSize: 36,
            color: "rgba(226,232,240,0.68)",
            fontFamily: "Georgia, serif",
            fontStyle: "italic",
          }}
        >
          Daily Bible Verses · KJV
        </div>
      </div>

      {/* Audio track */}
      <Audio src={staticFile(data.audio)} />
    </AbsoluteFill>
  );
};
