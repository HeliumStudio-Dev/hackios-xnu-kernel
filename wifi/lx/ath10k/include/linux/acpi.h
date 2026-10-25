#ifndef _ATH10K_COMPAT_ACPI_H
#define _ATH10K_COMPAT_ACPI_H
#include_next <linux/acpi.h>
#undef ACPI_HANDLE
#define ACPI_HANDLE(dev) NULL
#endif
