AMAZON_FREERTOS_LIB_DIR := ../../../../../../../lib

COMPONENT_SRCDIRS := .
COMPONENT_ADD_INCLUDEDIRS := include

ifdef CONFIG_TCPIP_FREERTOS_STACK
COMPONENT_SRCDIRS += $(AMAZON_FREERTOS_LIB_DIR)/secure_sockets/portable/freertos_plus_tcp
COMPONENT_OBJEXCLUDE := tcpip_adapter_lwip.o
COMPONENT_PRIV_INCLUDEDIRS := $(AMAZON_FREERTOS_LIB_DIR)/third_party/pkcs11
endif

ifdef CONFIG_TCPIP_LWIP
COMPONENT_SRCDIRS += $(AMAZON_FREERTOS_LIB_DIR)/secure_sockets/portable/lwip
COMPONENT_OBJEXCLUDE := tcpip_adapter_freertos.o
endif
