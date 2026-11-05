#---------------------------------------------------------------------------------
# Launcher do BO2 Requiem NX (libnx). Use build.sh, que gera os assets antes.
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITPRO)),)
$(error "Defina DEVKITPRO (ou use build.sh, que compila no container devkitpro/devkita64)")
endif

TOPDIR ?= $(CURDIR)
include $(DEVKITPRO)/libnx/switch_rules

ASSETS      ?= assets
TARGET      := launcher
BUILD       := build
SOURCES     := source
INCLUDES    := include
ROMFS       := $(ASSETS)/romfs
ICON        := $(ASSETS)/icon.jpg
APP_TITLE   := Black Ops II
APP_AUTHOR  := Requiem NX + mods
APP_VERSION := 1.0.0

ARCH     := -march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft -fPIE
CFLAGS   := -g -Wall -Wextra -Wno-unused-parameter -O2 -ffunction-sections $(ARCH) $(DEFINES) $(INCLUDE) -D__SWITCH__
ASFLAGS  := -g $(ARCH)
LDFLAGS   = -specs=$(DEVKITPRO)/libnx/switch.specs -g $(ARCH) -Wl,-Map,$(notdir $*.map)
LIBS     := -lnx -lm
LIBDIRS  := $(PORTLIBS) $(LIBNX)

ifneq ($(BUILD),$(notdir $(CURDIR)))

export OUTPUT   := $(CURDIR)/$(TARGET)
export TOPDIR   := $(CURDIR)
export VPATH    := $(foreach dir,$(SOURCES),$(CURDIR)/$(dir))
export DEPSDIR  := $(CURDIR)/$(BUILD)
CFILES          := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
export LD       := $(CC)
export OFILES   := $(CFILES:.c=.o)
export INCLUDE  := $(foreach dir,$(INCLUDES),-I$(CURDIR)/$(dir)) $(foreach dir,$(LIBDIRS),-I$(dir)/include) -I$(CURDIR)/$(BUILD)
export LIBPATHS := $(foreach dir,$(LIBDIRS),-L$(dir)/lib)
export APP_ICON := $(TOPDIR)/$(ICON)
export NROFLAGS += --icon=$(APP_ICON) --nacp=$(CURDIR)/$(TARGET).nacp --romfsdir=$(CURDIR)/$(ROMFS)

.PHONY: $(BUILD) clean all
all: $(BUILD)

$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

clean:
	@rm -fr $(BUILD) $(TARGET).nro $(TARGET).nacp $(TARGET).elf

else

DEPENDS := $(OFILES:.o=.d)

all: $(OUTPUT).nro
$(OUTPUT).nro: $(OUTPUT).elf $(OUTPUT).nacp
$(OUTPUT).elf: $(OFILES)

-include $(DEPENDS)

endif
