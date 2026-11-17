# Package metadata.
TITLE       := 4PT
VERSION     := 2.75
TITLE_ID    := PAPT00275

CONTENT_ID  := IV0000-PAPT00275_00-PSAAPTPKG0000000
PROJNAME    := 4PT

# Libraries linked into the ELF.
LIBS        :=  -lc -lkernel -lc++ -lSceAudioOut -lSceSysmodule -lSceSysCore -lSceSystemService -lSceUserService -lSceAppInstUtil -lSceBgft -lSceVideoOut -lSceFreeType -lScePad -lyaml-cpp -lSceNetCtl -lSceNet -lSceSsl -lSceHttp -lSceCommonDialog -lSceMsgDialog -lSceIme -lSceImeDialog -ljbc

# Additional compile flags.
EXTRAFLAGS  := -DGRAPHICS_USES_FONT

# Asset and module directories.
ASSETS    := $(shell find assets -type f -name '*.*')
LIBMODULES        := $(shell find sce_module -type f -name '*.*')

# You likely won't need to touch anything below this point.

# Root vars
TOOLCHAIN   := $(OO_PS4_TOOLCHAIN)
PROJDIR     := $(CURDIR)/src
COMMONDIR   := $(TOOLCHAIN)/samples/_common
INTDIR      := $(CURDIR)/build

# Discover every source exactly once and preserve its directory in build/.
SOURCES     := $(shell find $(PROJDIR) -type f \( -name '*.c' -o -name '*.cpp' \))
CFILES      := $(filter %.c,$(SOURCES))
CPPFILES    := $(filter %.cpp,$(SOURCES))
OBJS        := $(patsubst $(PROJDIR)/%.c,$(INTDIR)/%.o,$(CFILES)) \\
               $(patsubst $(PROJDIR)/%.cpp,$(INTDIR)/%.o,$(CPPFILES))
OUTS        := $(OBJS)

# Create the intermediate directory in case it does not already exist.
_unused     := $(shell mkdir -p $(INTDIR))


# Define final C/C++ flags
CFLAGS      := --target=x86_64-pc-freebsd12-elf -fPIC -funwind-tables -c $(EXTRAFLAGS) -isysroot $(TOOLCHAIN) -isystem $(TOOLCHAIN)/include
CXXFLAGS    := $(CFLAGS) -isystem $(TOOLCHAIN)/include/c++/v1
LDFLAGS     := -m elf_x86_64 -pie --script $(TOOLCHAIN)/link.x --eh-frame-hdr -L$(TOOLCHAIN)/lib $(LIBS) $(TOOLCHAIN)/lib/crt1.o

# Check for linux vs macOS and account for clang/ld path
UNAME_S     := $(shell uname -s)

ifeq ($(UNAME_S),Linux)
		CC      := clang
		CCX     := clang++
		LD      := ld.lld
		CDIR    := linux
endif
ifeq ($(UNAME_S),Darwin)
		CC      := /usr/local/opt/llvm@9/bin/clang
		CCX     := /usr/local/opt/llvm@9/bin/clang++
		LD      := /usr/local/opt/llvm@9/bin/ld.lld
		CDIR    := macos
endif

.PHONY: all clean check-toolchain

all: check-toolchain $(CONTENT_ID).pkg sce_sys/param.sfo
	rm -r $(INTDIR)
	rm -r pkg.gp4
	rm -r sce_sys/param.sfo
	rm -r eboot.bin
$(CONTENT_ID).pkg: pkg.gp4
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core pkg_build $< .

pkg.gp4: eboot.bin sce_sys/about/right.sprx sce_sys/param.sfo sce_sys/icon0.png sce_sys/pic0.png sce_sys/pic1.png $(LIBMODULES) $(ASSETS)
	$(TOOLCHAIN)/bin/$(CDIR)/create-gp4 -o $@ -c $(CONTENT_ID) $^
sce_sys/param.sfo: Makefile
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_new $@
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ APP_TYPE --type Integer --maxsize 4 --value 0
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ APP_VER --type Utf8 --maxsize 8 --value '$(VERSION)'
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ ATTRIBUTE --type Integer --maxsize 4 --value 18
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ ATTRIBUTE2 --type Integer --maxsize 4 --value 2
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ CATEGORY --type Utf8 --maxsize 4 --value 'gde'
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ CONTENT_ID --type Utf8 --maxsize 48 --value '$(CONTENT_ID)'
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ DOWNLOAD_DATA_SIZE --type Integer --maxsize 4 --value 0 
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ SYSTEM_VER --type Integer --maxsize 4 --value 0  
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ TITLE --type Utf8 --maxsize 128 --value '$(TITLE)'
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ TITLE_ID --type Utf8 --maxsize 12 --value '$(TITLE_ID)'
	$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core sfo_setentry $@ VERSION --type Utf8 --maxsize 8 --value '$(VERSION)'

eboot.bin: $(INTDIR) $(OBJS)
	$(LD) $(OUTS) -o $(INTDIR)/$(PROJNAME).elf $(LDFLAGS)
	$(TOOLCHAIN)/bin/$(CDIR)/create-eboot -in=$(INTDIR)/$(PROJNAME).elf
	$(TOOLCHAIN)/bin/$(CDIR)/create-fself $(INTDIR)/$(PROJNAME).oelf eboot.bin --paid 0x3800000000000011

check-toolchain:
	@test -n "$(TOOLCHAIN)" || (echo "Set OO_PS4_TOOLCHAIN to the OpenOrbis toolchain directory"; exit 1)
	@test -x "$(TOOLCHAIN)/bin/$(CDIR)/PkgTool.Core" || (echo "PkgTool.Core not found under $(TOOLCHAIN)/bin/$(CDIR)"; exit 1)

$(INTDIR)/%.o: $(PROJDIR)/%.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -o $@ $<

$(INTDIR)/%.o: $(PROJDIR)/%.cpp
	@mkdir -p $(dir $@)
	$(CCX) $(CXXFLAGS) -o $@ $<

#$(INTDIR)/%.o: $(COMMONDIR)/%.c
#	$(CCX) $(CXXFLAGS) -o $@ $<

#$(INTDIR)/%.o: $(COMMONDIR)/%.cpp
#	$(CCX) $(CXXFLAGS) -o $@ $<

clean:
	rm -rf $(CONTENT_ID).pkg sce_sys/param.sfo build eboot.bin
