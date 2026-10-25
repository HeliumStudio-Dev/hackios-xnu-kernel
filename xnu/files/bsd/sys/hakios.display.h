/*
 * Where the panel's scan is (bsd/dev/hakios.display.c, boot-arg fb_scan=1): for the framebuffer driver
 * (iokit/Kernel/MiniIOMobileFramebuffer.cpp), so that frames go into the panel's memory where the scan lets
 * them land whole, at the panel's own rate.
 */
#ifndef _SYS_HAKIOS_DISPLAY_H_
#define _SYS_HAKIOS_DISPLAY_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct hakios_display_scan {
	int ok;
	uint32_t lines;                 /* lines a frame, the blanking included (2432) */
	uint32_t shown;                 /* of which shown (2400): lines 0..shown-1, then the blanking */
	uint32_t millihz;               /* frames a second, in thousandths (119930) */
	uint64_t line_ns, frame_ns;
};

int hakios_display_scan_start(void);                           /* 1 when the scan can be read */
const struct hakios_display_scan *hakios_display_scan(void);  /* NULL without */
uint32_t hakios_display_line(uint32_t *frame);                 /* video line or command TE phase tick; command frame is 0 */
uint64_t hakios_display_next_frame_ns(void);                   /* until the next frame's first line */

#ifdef __cplusplus
}
#endif

#endif /* _SYS_HAKIOS_DISPLAY_H_ */
