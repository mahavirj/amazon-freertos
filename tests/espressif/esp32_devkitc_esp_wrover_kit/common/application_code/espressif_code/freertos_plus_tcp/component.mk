AMAZON_FREERTOS_LIB_DIR := ../../../../../../../lib
AMAZON_FREERTOS_DEMOS_DIR := ../../../../../../../demos

COMPONENT_SRCDIRS :=
COMPONENT_ADD_INCLUDEDIRS := 
ifdef CONFIG_TCPIP_FREERTOS_STACK
COMPONENT_SRCDIRS += $(AMAZON_FREERTOS_LIB_DIR)/FreeRTOS-Plus-TCP/source \
                    $(AMAZON_FREERTOS_LIB_DIR)/FreeRTOS-Plus-TCP/source/portable/BufferManagement \
                    $(AMAZON_FREERTOS_LIB_DIR)/FreeRTOS-Plus-TCP/source/portable/NetworkInterface/esp32 \

COMPONENT_ADD_INCLUDEDIRS += $(AMAZON_FREERTOS_LIB_DIR)/FreeRTOS-Plus-TCP/include \
                            $(AMAZON_FREERTOS_LIB_DIR)/FreeRTOS-Plus-TCP/source/portable/Compiler/GCC \
                            $(AMAZON_FREERTOS_DEMOS_DIR)/common/include

COMPONENT_OBJEXCLUDE := $(AMAZON_FREERTOS_LIB_DIR)/FreeRTOS-Plus-TCP/source/portable/BufferMangement/BufferAllocation_1.o
demos/common/tcp/aws_tcp_echo_client_single_task.o: CFLAGS+=-Wno-format
endif
