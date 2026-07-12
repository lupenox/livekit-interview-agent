'use client';

import { FormEvent, useState } from 'react';
import { ArrowRight, AudioLines, BrainCircuit, CheckCircle2, Mic2 } from 'lucide-react';
import { ConnectionDetails, InterviewRoom } from '@/components/interview-room';

export default function HomePage() {
  const [participantName, setParticipantName] = useState('Logan');
  const [targetRole, setTargetRole] = useState('AI Engineer');
  const [connection, setConnection] = useState<ConnectionDetails | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState('');

  async function startInterview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setIsStarting(true);

    try {
      const response = await fetch('/api/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ participantName, targetRole }),
      });

      const body = await response.json();
      if (!response.ok) throw new Error(body.error || 'Unable to start the interview.');
      setConnection(body as ConnectionDetails);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : 'Unable to start the interview.');
    } finally {
      setIsStarting(false);
    }
  }

  if (connection) {
    return <InterviewRoom connection={connection} targetRole={targetRole} onLeave={() => setConnection(null)} />;
  }

  return (
    <main className="landing-shell">
      <nav className="top-nav">
        <div className="brand-mark"><Mic2 size={20} /><span>MockMate</span></div>
        <span className="prototype-pill">Portfolio MVP</span>
      </nav>

      <section className="hero-grid">
        <div className="hero-copy">
          <div className="eyebrow">Real-time AI interview practice</div>
          <h1>Practice out loud.<br /><span>Interview with confidence.</span></h1>
          <p className="hero-description">A patient voice interviewer that listens to complete answers, asks focused follow-ups, and helps you rehearse the stories that get candidates hired.</p>

          <div className="feature-row">
            <div><AudioLines /><span>Natural voice conversation</span></div>
            <div><BrainCircuit /><span>Role-aware follow-ups</span></div>
            <div><CheckCircle2 /><span>No account required</span></div>
          </div>
        </div>

        <form className="setup-card" onSubmit={startInterview}>
          <div className="setup-heading">
            <span>Start a practice session</span>
            <small>About 3–5 minutes</small>
          </div>

          <label>
            Your name
            <input value={participantName} onChange={(event) => setParticipantName(event.target.value)} required maxLength={60} />
          </label>

          <label>
            Target role
            <input value={targetRole} onChange={(event) => setTargetRole(event.target.value)} required maxLength={100} />
          </label>

          <div className="permission-note"><Mic2 size={18} /><span>Your browser will ask for microphone permission when the session begins.</span></div>

          {error && <p className="error-message">{error}</p>}

          <button className="primary-button" type="submit" disabled={isStarting}>
            {isStarting ? 'Preparing room…' : 'Begin interview'}
            {!isStarting && <ArrowRight size={19} />}
          </button>
        </form>
      </section>

      <section className="proof-strip">
        <span>LiveKit WebRTC</span><span>Deepgram STT</span><span>Groq Llama</span><span>ElevenLabs TTS</span>
      </section>
    </main>
  );
}
