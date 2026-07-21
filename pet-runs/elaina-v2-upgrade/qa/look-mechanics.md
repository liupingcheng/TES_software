# Elaina look mechanics

Elaina is a tiny humanoid pixel-art witch/mage. Her lower torso, boots, planted baseline, wand hand, and wand contact point stay anchored. The eyes lead each gaze; eyelids and brows reshape by a few pixels, then the head and neck follow with a restrained yaw or pitch. Her long silver hair follows the head by one small step and keeps its volume. The wand remains rigid and attached to the viewer-left hand, lagging only subtly with the upper body; the free hand stays attached at the hip. Preserve facial proportions and do not warp the skull, clothing, hands, hair, or wand.

Motion budget: every 22.5-degree step changes the pupils/eye surfaces first, then head angle and hair silhouette by roughly the same small visual amount. Keep the feet, body scale, baseline, and center registration fixed. No whole-sprite rotation, affine tilt, new props, detached effects, shadows, labels, or guide marks.

Cardinal pose families:

- `000 up`: both eyes and eyelids clearly aim upward; chin lifts slightly; bangs reveal a little more eye area; the upper hair shifts subtly downward/back while both body sides remain balanced. The wand stays fixed in the viewer-left hand.
- `090 screen-right`: pupils, nose, face plane, and chin turn unmistakably toward the viewer's screen-right. The screen-left side of the head/hair becomes slightly more visible while the far screen-right cheek/eye compresses or is mildly occluded. The wand stays attached and lags subtly.
- `180 down`: both eyes aim downward; upper lids lower; chin tucks; bangs and front hair overlap slightly more of the forehead/eyes. The torso and feet remain fixed and the wand stays attached.
- `270 screen-left`: pupils, nose, face plane, and chin turn unmistakably toward the viewer's screen-left. The screen-right side of the head/hair becomes slightly more visible while the far screen-left cheek/eye compresses or is mildly occluded. The viewer-left wand remains attached and may become slightly more side-on without switching hands.

Diagonals interpolate those four families evenly. Every adjacent pose must preserve Elaina's face, silver hair, white-and-gold outfit, dark boots, wand design, pixel scale, and anchored lower body. `337.5` must be exactly one restrained step before the approved `000` pose, and `157.5` exactly one step before `180`.

Repair strategy after recurrent continuity failure: keep the horizontal cardinals unmistakable clean profiles with the nose pointing to the literal image edge. Continuity between the right profile and down cardinal will be grounded by an additional coherent `090, 112.5, 135, 157.5` transition strip so the full row can interpolate through explicit pose families instead of inventing the return in one step.
