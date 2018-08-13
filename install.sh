#!/usr/bin/env bash

set -x

current_dir=$(pwd)

# ads1256 library dependencies
cd /tmp
apt-get install automake libtool -y
wget http://www.airspayce.com/mikem/bcm2835/bcm2835-1.56.tar.gz
tar zxvf bcm2835-1.56.tar.gz
cd bcm2835-1.56
./configure
make
make check
make install
rm -rf /tmp/bcm2835-1.56

# ads1256 library
apt-get install git build-essential python-dev -y
cd /tmp
git clone https://github.com/fabiovix/py-ads1256.git
cd py-ads1256
python setup.py install
rm -rf /tmp/py-ads1256

# Enable the gpio-shutdown overlay
grep -q "^dtoverlay=gpio-shutdown" /boot/config.txt || echo 'dtoverlay=gpio-shutdown' >> /boot/config.txt

# Few tweaks to store logs on an external flash disk (USB stick)
mkdir -p /media/datalogs
grep -q "/media/datalogs" /etc/fstab || echo "/dev/sda1 /media/datalogs auto defaults 0 0" >> /etc/fstab
mount /media/datalogs
mkdir -p /media/datalogs/pimonitor-log

# Get the pimonitor dependencies
mkdir -p /srv/pilogger/data
cd /tmp
git clone https://github.com/PiMonitor/PiMonitor.git
cp -r PiMonitor/pimonitor /usr/local/lib/python2.7/dist-packages/
cp PiMonitor/data/* /srv/pilogger/data/
rm -rf /tmp/PiMonitor

# Monkey patch pimonitor for logging.
cd $current_dir
cp tools/logging/PM.py /usr/local/lib/python2.7/dist-packages/pimonitor/PM.py

apt-get install python-pip -y
pip install pyserial

# Install my the pilogger
cp tools/logging/PMLog.py /srv/pilogger/
cp install/logger_STD_EN_v336.xml /srv/pilogger/data/

cp install/pilogger.service /lib/systemd/system/pilogger.service
systemctl enable pilogger.service
systemctl start pilogger.service
