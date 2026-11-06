#pragma once
/* Navigation sound: romfs:/nav.pcm (48 kHz, 16-bit, stereo; made by make_assets.py from
 * the original launcher's UInavigate.mp3), played with audout. Silent if missing. */

void sound_init(void);
void sound_play(void);
void sound_exit(void);
