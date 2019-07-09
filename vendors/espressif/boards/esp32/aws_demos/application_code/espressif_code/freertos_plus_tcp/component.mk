AMAZON_FREERTOS_ABSTRACTIONS_DIR := ../../../../../../../../libraries/abstractions
AMAZON_FREERTOS_ARF_PLUS_DIR := ../../../../../../../../libraries/freertos_plus
AMAZON_FREERTOS_DEMOS_DIR := ../../../../../../../../demos


COMPONENT_SRCDIRS :=
COMPONENT_ADD_INCLUDEDIRS := 
ifdef CONFIG_TCPIP_FREERTOS_STACK
COMPONENT_SRCDIRS += $(AMAZON_FREERTOS_ARF_PLUS_DIR)/standard/freertos_plus_tcp/source \
                    $(AMAZON_FREERTOS_ARF_PLUS_DIR)/standard/freertos_plus_tcp/source/portable/BufferManagement \
                    $(AMAZON_FREERTOS_ARF_PLUS_DIR)/standard/freertos_plus_tcp/source/portable/NetworkInterface/esp32 \
                    $(AMAZON_FREERTOS_DEMOS_DIR)/tcp \

COMPONENT_ADD_INCLUDEDIRS += $(AMAZON_FREERTOS_ARF_PLUS_DIR)/standard/freertos_plus_tcp/include \
                            $(AMAZON_FREERTOS_ARF_PLUS_DIR)/standard/freertos_plus_tcp/source/portable/Compiler/GCC \
                            $(AMAZON_FREERTOS_DEMOS_DIR)/common/include

COMPONENT_OBJEXCLUDE := $(AMAZON_FREERTOS_ARF_PLUS_DIR)/standard/freertos_plus_tcp/source/portable/BufferManagement/BufferAllocation_1.o
demos/tcp/aws_tcp_echo_client_single_task.o: CFLAGS+=-Wno-format
endif
