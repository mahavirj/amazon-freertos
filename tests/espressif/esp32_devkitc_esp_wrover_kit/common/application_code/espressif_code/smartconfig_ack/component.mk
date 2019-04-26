#
# Component Makefile

COMPONENT_INCLUDEDIRS := include
COMPONENT_SRCDIRS := .

ifdef CONFIG_TCPIP_FREERTOS_STACK
COMPONENT_OBJS := smartconfig_ack_freertos.o
endif

ifdef CONFIG_TCPIP_LWIP
COMPONENT_OBJS := smartconfig_ack_lwip.o
endif
