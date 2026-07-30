import PachinkoTrack, { genPachinkoRings, pachinkoCams } from './PachinkoTrack.jsx'
import FunnelTrack, { genFunnelRings, funnelCams } from './FunnelTrack.jsx'
import SonicTrack, { genSonicRings, sonicCams } from './SonicTrack.jsx'

/** The swappable drop sections (the user's sketch): what happens to every
 * ball after the deck, on its way to the boss. */
export const DROP_TRACKS = {
  pachinko: { name: '柏青哥', Component: PachinkoTrack, genRings: genPachinkoRings, cams: pachinkoCams },
  funnel: { name: '漩渦大砲', Component: FunnelTrack, genRings: genFunnelRings, cams: funnelCams },
  sonic: { name: '音速迴圈', Component: SonicTrack, genRings: genSonicRings, cams: sonicCams },
}
