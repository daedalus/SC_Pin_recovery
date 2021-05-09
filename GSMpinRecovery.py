#!/usr/env python3
# Author Dario Clavijo 2021
# GPLv3

import logging
import argparse
import sys
import time
import humanfriendly
import signal
import base64
import os

from smartcard.System import readers
from smartcard.CardType import AnyCardType
from smartcard.CardRequest import CardRequest
from smartcard.util import toHexString, toBytes

class Attack:
    def __init__(
        self,
        connection,
        startpin,
        digits,
        wait,
        reset=None,
        rcpt=None,
        sender=None,
        verbose=False,
    ):
        self.wait = wait
        self.reset = reset
        self.startpin = startpin
        self.ns = startpin
        self.l = digits
        self.stoping = False
        self.Continue = True
        self.Found = False
        self.connection = connection
        self.rcpt = rcpt
        self.sender = sender
        self.fp = None
        self.verbose = verbose

    def save(self):
        n = self.nc
        if self.fp == None:
            self.fp = open(".GSMpinRecovery.save", "w")
            self.fp.write("%d\n" % self.nc)
            self.fp.close()
            self.fp = None

    def sendmail(self, body, recipient, subject, sender):
        b64 = base64.b64encode(body.encode("ascii")).decode("ascii")
        cmd = "echo %s | base64 -d | gpg -ea -r '%s' | mail %s -s '%s' -r '%s'" % (
            b64,
            recipient,
            recipient,
            subject,
            sender,
        )
        if self.verbose:
            print(cmd)
        os.system(cmd)

    def runtime(self):
        td = time.time() - self.ti
        nd = self.nc - self.ns
        ndtd = nd / td
        htd = humanfriendly.format_timespan(td)
        r = "[+] Runtime: %s, tried pins: %d, rate: %.4f pin/s.   " % (htd, nd, ndtd)
        return r

    def signal_handler(self, sig, frame):
        self.stoping = True
        print("[!] You pressed Ctrl+C!  ")

    def ResetChip(self):
        RSET = [
            0x3B,
            0x9F,
            0x96,
            0x80,
            0x1F,
            0xC6,
            0x80,
            0x31,
            0xE0,
            0x73,
            0xFE,
            0x21,
            0x1B,
            0x64,
            0x41,
            0x04,
            0x81,
            0x00,
            0x82,
            0x90,
            0x00,
            0x04,
        ]
        data, sw1, sw2 = self.xmit(RSET)

    def xmit(self, Command):
        if not self.stoping:
            try:
                r = self.connection.transmit(Command)  # send the command
            except:
                if self.stoping == False:
                    print(
                        "[!] Connection error!, last pin checked: %d." % (self.nc - 1)
                    )
                    self.stoping = True
                r = None
        else:
            r = None
        return r

    def encode_pin_cmd(self, n, s):
        N = s % n
        A = 0x30 + int(N[0])
        B = 0x30 + int(N[1])
        C = 0x30 + int(N[2])
        D = 0x30 + int(N[3])
        E = 0xFF
        F = 0xFF
        G = 0xFF
        H = 0xFF

        if l > 4:
            E = 0x30 + int(N[4])
        if l > 5:
            F = 0x30 + int(N[5])
        if l > 6:
            G = 0x30 + int(N[6])
        if l > 7:
            H = 0x30 + int(N[7])

        COMM = [
            0xA0,
            0x20,
            0x00,
            0x01,
            0x08,
            A,
            B,
            C,
            D,
            E,
            F,
            G,
            H,
        ]  # APDU with command pkt

        return COMM

    def crack_pin(self):
        """The function just forms a APDU with the pin then sends it to the reader and waits for the status."""
        self.ti = time.time()
        n = self.startpin
        L = 10 ** (l) - 1
        c = True
        s = "X%dd" % l
        s = s.replace("X", "%0")
        print(
            "[+] startpin: %d, max: %d, wait: %s, reset: %s"
            % (n, L, str(self.wait), str(self.reset))
        )

        while n <= L and self.Continue:  # keep looping if the c is set
            self.nc = n
            COMM = self.encode_pin_cmd(n, s)
            r = self.xmit(COMM)
            if r != None:
                data, sw1, sw2 = r
                if not self.stoping:
                    if self.verbose:
                        scommand = str(list(map(hex, COMM)))
                        sys.stderr.write(
                            "Pin: %d, Command: %s, Status: %02x %02x\r"
                            % (n, scommand, sw1, sw2)
                        )
                    else:
                        sys.stderr.write("Pin: %d\r" % n)
                self.Continue = (
                    sw1 == 0x98 and sw2 == 0x08
                )  # if invalid pin then c=True
                self.Found = not self.Continue

                if sw2 == 0x40:  # status for card blocked
                    print("[!] Card blocked, check PUK!...")
                    self.stoping = True
                    self.Found = False
            else:
                # c = False
                self.stoping = True
                self.Found = False

            if self.Found:  # Status for successful attack
                b = "The PIN is: [ %d ]!!!\n%s\n" % (n,self.runtime())
                print(b)
                self.stoping = True
                if self.rcpt:
                    self.sendmail(b, self.rcpt, "Check this!!!", self.sender)

            if self.wait != None:
                time.sleep(self.wait)

            n += 1

            if (
                self.reset != None and reset > 0 and n % self.reset == 0
            ):  # reset the chip
                self.ResetChip()

            if n % 10000 == 0:
                self.save()

            if self.stoping == True:
                if not self.Found:
                    print(self.runtime())  # prints runtime information
                self.Continue = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GSM Pin recovery tool")
    parser.add_argument("--startpin", help="Pin to be cracked.")
    parser.add_argument("--lenght", help="Lenght of the Pin to be cracked.", default=4)
    parser.add_argument("--wait", help="Wait in seconds")
    parser.add_argument("--reset", help="Reset the chip after n tries")
    parser.add_argument("--rcpt", help="Recipient of email")
    parser.add_argument("--sender", help="Sender of the email")
    parser.add_argument("--verbose", help="Verbose output", action="store_true")


    args = parser.parse_args()

    def getConnection():
        r = readers()
        print("[+] Reader:", r)
        cardtype = AnyCardType()
        cardrequest = CardRequest( timeout=60, cardType=cardtype )
        print("[!] Waiting for card...")
        try:
            cardservice = cardrequest.waitforcard()
        except:
            cardservice = None
            connection = None
        if cardservice:
            connection = r[0].createConnection()
            connection.connect()
            print("[+] Card ATR is: [ %s ]" % toHexString(connection.getATR()))
        return connection

    connection = getConnection()

    if connection == None:
        print("[!] Could not get connection to the card, check your reader...")
        sys.exit(-1)

    if args.startpin:
        # n= 00274710
        n = int(args.startpin)
    else:
        n = 0

    if args.lenght:
        if 4 <= int(args.lenght) <= 8:
            l = int(args.lenght)
        else:
            print("[!] Pin lenght shoul be between 4 and 8")
            sys.exit(-1)
    else:
        l = 4

    attack = Attack(
        connection,
        n,
        l,
        args.wait,
        reset=args.reset,
        rcpt=args.rcpt,
        sender=args.sender,
        verbose=args.verbose
    )
    signal.signal(signal.SIGINT, attack.signal_handler)
    attack.crack_pin()
    print("[-] Program end.")
