#include "sound.h"

#include <malloc.h>
#include <stdio.h>
#include <string.h>

#include <switch.h>

static AudioOutBuffer out;
static void *pcm;
static int ready, playing;

void sound_init(void)
{
    FILE *f = fopen("romfs:/nav.pcm", "rb");
    if (!f)
        return;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    /* audout wants the buffer and its size aligned to 0x1000 */
    size_t size = (n + 0xFFF) & ~0xFFF;
    pcm = n > 0 ? memalign(0x1000, size) : NULL;
    if (!pcm || fread(pcm, 1, n, f) != (size_t)n) {
        fclose(f);
        free(pcm);
        pcm = NULL;
        return;
    }
    fclose(f);
    memset((char *)pcm + n, 0, size - n);
    if (R_FAILED(audoutInitialize()))
        return;
    if (R_FAILED(audoutStartAudioOut())) {
        audoutExit();
        return;
    }
    out = (AudioOutBuffer){.buffer = pcm, .buffer_size = size, .data_size = n, .data_offset = 0};
    ready = 1;
}

/* plays the sound unless it is still playing (navigation repeats faster than it lasts) */
void sound_play(void)
{
    if (!ready)
        return;
    if (playing) {
        AudioOutBuffer *released = NULL;
        u32 count = 0;
        if (R_SUCCEEDED(audoutGetReleasedAudioOutBuffer(&released, &count)) && count)
            playing = 0;
        else
            return;
    }
    if (R_SUCCEEDED(audoutAppendAudioOutBuffer(&out)))
        playing = 1;
}

void sound_exit(void)
{
    if (ready) {
        audoutStopAudioOut();
        audoutExit();
        ready = 0;
    }
    free(pcm);
    pcm = NULL;
}
