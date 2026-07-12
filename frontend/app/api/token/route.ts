import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { AccessToken, type VideoGrant } from 'livekit-server-sdk';

export const dynamic = 'force-dynamic';

type TokenRequest = {
  participantName?: string;
  targetRole?: string;
};

export async function POST(request: Request) {
  try {
    const livekitUrl = process.env.LIVEKIT_URL;
    const apiKey = process.env.LIVEKIT_API_KEY;
    const apiSecret = process.env.LIVEKIT_API_SECRET;

    if (!livekitUrl || !apiKey || !apiSecret) {
      return NextResponse.json(
        { error: 'LiveKit server credentials are not configured.' },
        { status: 500 }
      );
    }

    const body = (await request.json().catch(() => ({}))) as TokenRequest;
    const participantName = body.participantName?.trim() || 'Candidate';
    const targetRole = body.targetRole?.trim() || 'Software Engineer';
    const roomName = `interview-${randomUUID()}`;
    const identity = `candidate-${randomUUID()}`;

    const token = new AccessToken(apiKey, apiSecret, {
      identity,
      name: participantName,
      ttl: '20m',
      metadata: JSON.stringify({ targetRole }),
    });

    const grant: VideoGrant = {
      room: roomName,
      roomJoin: true,
      canPublish: true,
      canSubscribe: true,
      canPublishData: true,
    };

    token.addGrant(grant);

    return NextResponse.json(
      {
        serverUrl: livekitUrl,
        participantToken: await token.toJwt(),
        roomName,
        participantName,
      },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch (error) {
    console.error('Failed to create LiveKit token', error);
    return NextResponse.json({ error: 'Unable to start the interview.' }, { status: 500 });
  }
}
