/* Raphael command-mode TE phase for refresh notifications; page flips retain the existing latch path. */
#include <kern/clock.h>
#include <libkern/libkern.h>
#include <mach/mach_types.h>
#include <machine/machine_routines.h>
#include <pexpert/pexpert.h>
#include <sys/hakios.display.h>
#include <sys/hakios.input.h>
#include <sys/systm.h>

static struct hakios_display_scan scan;
extern int raphael_display_scan_counter(uint32_t *line);

uint32_t
hakios_display_line(uint32_t *frame)
{
	uint32_t line;
	{
		if (frame != NULL) *frame = 0; /* Firmware's command-mode frame counter does not advance. */
		if (!scan.ok || !raphael_display_scan_counter(&line) || line > scan.lines + scan.lines / 4) {
			scan.ok = 0;
			return 0;
		}
		return line < scan.lines ? line : scan.lines - 1;
	}
	return 0;
}

const struct hakios_display_scan *
hakios_display_scan(void)
{
	if (scan.ok) (void)hakios_display_line(NULL);
	return scan.ok ? &scan : NULL;
}

uint64_t
hakios_display_next_frame_ns(void)
{
	uint32_t line;

	if (!scan.ok) {
		return 0;
	}
	line = hakios_display_line(NULL);
	if (!scan.ok) return 0;
	return (uint64_t)(scan.lines - line) * scan.line_ns;
}

static int
command_scan_start(void)
{
	uint32_t before, line, edges = 0;
	uint64_t start = mach_absolute_time(), previous = start, first = 0, last = 0;
	uint64_t elapsed = 0, ticks = 0, ns, dt;

	if (!raphael_display_scan_counter(&before)) return 0;
	while (edges < 3) {
		delay_for_interval(50, NSEC_PER_USEC);
		uint64_t now = mach_absolute_time();
		absolutetime_to_nanoseconds(now - start, &ns);
		if (ns > 150 * NSEC_PER_MSEC || !raphael_display_scan_counter(&line)) return 0;
		absolutetime_to_nanoseconds(now - previous, &dt);
		if (line < before) {
			if (dt >= NSEC_PER_MSEC) return 0; /* A delayed sample cannot identify which TE edge it saw. */
			if (edges++ == 0) first = now;
			last = now;
		} else if (dt < NSEC_PER_MSEC) {
			elapsed += dt;
			ticks += line - before;
		}
		before = line;
		previous = now;
	}
	if (ticks == 0) return 0;
	absolutetime_to_nanoseconds(last - first, &ns);
	scan.frame_ns = ns / 2;
	scan.line_ns = elapsed / ticks;
	if (scan.line_ns == 0 || scan.frame_ns < 4 * NSEC_PER_MSEC || scan.frame_ns > 50 * NSEC_PER_MSEC) return 0;
	scan.lines = (uint32_t)((scan.frame_ns + scan.line_ns / 2) / scan.line_ns);
	scan.shown = 2340;
	if (scan.lines < scan.shown || scan.lines > 0xffff) return 0;
	scan.millihz = (uint32_t)(1000000000000ULL / scan.frame_ns);
	scan.ok = 1;
	printf("display: raphael command TE: %u.%03u Hz, %u ticks/frame, %llu ns/tick; page flips retained (fb_scan=1)\n",
	    scan.millihz / 1000, scan.millihz % 1000, scan.lines, scan.line_ns);
	return 1;
}

int
hakios_display_scan_start(void)
{
	uint32_t on = 0;
	if (scan.ok) return 1;
	if (!hakios_is_raphael() || !PE_parse_boot_argn("fb_scan", &on, sizeof(on)) || on != 1) return 0;
	return command_scan_start();
}
