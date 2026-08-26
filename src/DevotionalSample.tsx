import React from "react";
import {
  AbsoluteFill,
  Audio,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Easing,
} from "remotion";
import { DEVOTIONAL } from "./devotionalSampleData";
import { resolvePalette } from "./palettes";

type DevotionalData = typeof DEVOTIONAL & { palette?: string };

const CANVAS = "#0B1120";
const INK = "#F8FAFC";
const MUTED = "rgba(226,232,240,0.42)";
const GOLD = "#E8C47A";
const HAIRLINE = "rgba(232,196,122,0.28)";

export const DevotionalSample: React.FC<{ devotionalData?: DevotionalData }> = ({ devotionalData }) => {
  const data = devotionalData ?? DEVOTIONAL;
  const palette = resolvePalette(data.palette);
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const seconds = frame / fps;

  const activeIndex = data.blocks.findIndex((block, index) => {
    const nextStart = data.blocks[index + 1]?.start ?? block.end;
    return seconds >= block.start && seconds < nextStart;
  });
  const safeActiveIndex = activeIndex >= 0 ? activeIndex : data.blocks.length - 1;
  const active = data.blocks[safeActiveIndex];
  const currentKind = active.kind;

  const bgScale = interpolate(frame, [0, durationInFrames], [1.04, 1.13], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const introSpring = spring({
    frame,
    fps,
    config: { damping: 16, mass: 0.6, stiffness: 88 },
  });
  const headerY = interpolate(introSpring, [0, 1], [30, 0]);
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 18, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ backgroundColor: CANVAS, opacity: fadeOut }}>
      <AbsoluteFill
        style={{
          transform: `scale(${bgScale})`,
          background: currentKind === "prayer" ? palette.prayerBackground : palette.background,
        }}
      />

      <div
        style={{
          position: "absolute",
          inset: 48,
          border: `2px solid ${HAIRLINE}`,
          borderRadius: 8,
        }}
      />

      <div
        style={{
          position: "absolute",
          top: 138,
          width: "100%",
          textAlign: "center",
          transform: `translateY(${headerY}px)`,
        }}
      >
        <div
          style={{
            fontSize: 44,
            fontWeight: 700,
            letterSpacing: 12,
            color: GOLD,
            fontFamily: "Georgia, serif",
          }}
        >
          {data.reference}
        </div>
        <div
          style={{
            marginTop: 20,
            fontSize: 27,
            letterSpacing: 5,
            color: "rgba(226,232,240,0.58)",
            fontFamily: "Arial, sans-serif",
            textTransform: "uppercase",
          }}
        >
          Daily Bible Verses · KJV
        </div>
      </div>

      {currentKind === "verse" ? (
        <VerseScene activeIndex={safeActiveIndex} data={data} />
      ) : (
        <TextScene block={active} />
      )}

      <div
        style={{
          position: "absolute",
          bottom: 142,
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
            fontSize: 34,
            color: "rgba(226,232,240,0.64)",
            fontFamily: "Georgia, serif",
            fontStyle: "italic",
          }}
        >
          Daily Bible Verses · KJV
        </div>
      </div>

      <Audio src={staticFile(data.audio)} />
    </AbsoluteFill>
  );
};

function TextScene({ block }: { block: DevotionalData["blocks"][number] | undefined }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = interpolate(frame, [0, 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const label = block?.kind === "opening" ? "A thought for today" : block?.kind ?? "";

  return (
    <div
      style={{
        position: "absolute",
        top: 410,
        left: 92,
        right: 92,
        opacity,
        transform: `translateY(${interpolate(frame, [0, 14], [22, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px)`,
      }}
    >
      <div
        style={{
          fontSize: 30,
          letterSpacing: 7,
          textTransform: "uppercase",
          color: GOLD,
          fontFamily: "Arial, sans-serif",
          marginBottom: 34,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: block?.kind === "prayer" ? 68 : 76,
          lineHeight: 1.28,
          fontWeight: 600,
          color: INK,
          fontFamily: "Georgia, 'Times New Roman', serif",
        }}
      >
        {block?.text}
      </div>
    </div>
  );
}

function VerseScene({ activeIndex, data }: { activeIndex: number; data: DevotionalData }) {
  const verseBlocks = data.blocks.filter((block) => block.kind === "verse");
  return (
    <div
      style={{
        position: "absolute",
        top: 350,
        left: 82,
        right: 82,
        display: "flex",
        flexDirection: "column",
        gap: 24,
      }}
    >
      {verseBlocks.map((block) => {
        const globalIndex = data.blocks.findIndex((candidate) => candidate.index === block.index);
        const isActive = globalIndex === activeIndex;
        const isSpoken = activeIndex > globalIndex;
        return (
          <div
            key={block.index}
            style={{
              fontSize: 68,
              lineHeight: 1.24,
              fontWeight: isActive ? 700 : 600,
              color: isActive ? GOLD : isSpoken ? INK : MUTED,
              transform: `scale(${isActive ? 1.012 : 1})`,
              transformOrigin: "center left",
              textShadow: isActive ? "0 0 34px rgba(232,196,122,0.3)" : "none",
            }}
          >
            {block.text}
          </div>
        );
      })}
    </div>
  );
}
