/**
 * The boss at the end of the pachinko drop. Swap this object (textures +
 * numbers) to field a different victim — the BossFace component and all
 * damage logic read only from here.
 */
export const BOSS = {
  key: 'horus',
  name: '荷魯斯',
  textures: {
    // bruise stages, escalating with cumulative damage this game
    stages: [
      '/static/game/tex/horus_face_0.png',
      '/static/game/tex/horus_face_1.png',
      '/static/game/tex/horus_face_2.png',
    ],
    laugh: '/static/game/tex/horus_laugh.png',
  },
  bruiseAt: [250, 600],   // cumulative damage → stage 1, stage 2
  laughBelow: 50,          // a ball dealing less than this gets mocked
  taunts: ['就這樣？', '不痛不癢！', '哈哈哈哈！', '你在搔癢嗎？'],
}

/** Damage tier for presentation (colors / fx scale). */
export function damageTier(damage) {
  if (damage >= 300) return 'gold'
  if (damage >= 200) return 'purple'
  if (damage >= 100) return 'blue'
  if (damage >= 50) return 'plain'
  return 'weak'
}
