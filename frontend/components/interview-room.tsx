'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  BarVisualizer,
  ControlBar,
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
} from '@livekit/components-react';
import { ShieldCheck, Sparkles, TimerReset } from 'lucide-react';

import { CreditsHealth } from './credits-health';

export type ConnectionDetails = {
  serverUrl: string;
  participantToken: string;
  roomName: string;
  participantName: string;
};

type InterviewRoomProps = {
  connection: ConnectionDetails;
  targetRole: string;
  onLeave: () => void;
};

export function InterviewRoom({ connection, targetRole, onLeave }: InterviewRoomProps) {
  return (
    <LiveKitRoom
      token={connection.participantToken}
      serverUrl={connection.serverUrl}
      connect
      audio
      video={false}
      onDisconnected={onLeave}
      data-lk-theme="default"
      className="livekit-shell"
    >
      <InterviewExperience targetRole={targetRole} onLeave={onLeave} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

function InterviewExperience({ targetRole, onLeave }: { targetRole: string; onLeave: () => void }) {
  const { state, audioTrack } = useVoiceAssistant();
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setElapsedSeconds((seconds) => seconds + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const elapsed = useMemo(() => {
    const minutes = Math.floor(elapsedSeconds / 60).toString().padStart(2, '0');
    const seconds = (elapsedSeconds % 60).toString().padStart(2, '0');
    return `${minutes}:${seconds}`;
  }, [elapsedSeconds]);

  const statusCopy: Record<string, string> = {
    disconnected: 'Connecting to interviewer…',
    connecting: 'Connecting to interviewer…',
    initializing: 'Preparing the interview…',
    listening: 'Listening — take your time',
    thinking: 'Considering your answer…',
    speaking: 'Interviewer is speaking',
    failed: 'Connection needs attention',
  };
  const statusMessage = statusCopy[state] ?? 'Interview in progress';

  return (
    <main className="interview-layout">
      <header className="interview-header">
        <div>
          <div className="eyebrow">Live interview</div>
          <h1>{targetRole}</h1>
        </div>
        <div className="interview-header-actions">
          <CreditsHealth />
          <div className="timer-pill"><TimerReset size={17} />{elapsed}</div>
        </div>
      </header>

      <section className="interviewer-card" aria-live="polite">
        <div className={`avatar-orbit avatar-${state}`}>
          <div className="avatar-core"><Sparkles size={36} /></div>
        </div>
        <div className="stage-label">AI Interviewer</div>
        <h2>{statusMessage}</h2>
        <p>Answer naturally. The interviewer will wait through short pauses before replying.</p>
        <div className="visualizer-frame">
          <BarVisualizer
            state={state}
            barCount={7}
            trackRef={audioTrack}
            options={{ minHeight: 8 }}
          />
        </div>
      </section>

      <aside className="session-note">
        <ShieldCheck size={19} />
        <div><strong>Private practice room</strong><span>Your browser joins a temporary LiveKit room for this session.</span></div>
      </aside>

      <footer className="control-dock">
        <ControlBar
          controls={{ microphone: true, camera: false, screenShare: false, chat: false, leave: false }}
          variation="minimal"
        />
        <button className="end-button" type="button" onClick={onLeave}>End interview</button>
      </footer>
    </main>
  );
}
