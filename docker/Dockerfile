FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install AnyDesk from official APT repo — .deb pulls all dependencies automatically
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget ca-certificates gnupg2 xvfb iproute2 pciutils xdotool \
    && wget -qO- https://keys.anydesk.com/repos/DEB-GPG-KEY \
        | gpg --dearmor > /usr/share/keyrings/anydesk-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/anydesk-archive-keyring.gpg] http://deb.anydesk.com/ all main" \
        > /etc/apt/sources.list.d/anydesk.list \
    && apt-get update \
    && printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
    && chmod +x /usr/sbin/policy-rc.d \
    && apt-get install -y anydesk libpolkit-gobject-1-0 || true \
    && printf '#!/bin/sh\nexit 0\n' > /var/lib/dpkg/info/anydesk.postinst \
    && chmod 755 /var/lib/dpkg/info/anydesk.postinst \
    && dpkg --configure -a \
    && rm -f /usr/sbin/policy-rc.d \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/anydesk && chmod 777 /etc/anydesk

RUN useradd -m -s /bin/bash probeuser

COPY probe.sh /probe.sh
RUN chmod +x /probe.sh

ENTRYPOINT ["/probe.sh"]
