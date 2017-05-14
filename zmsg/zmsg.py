#!/usr/bin/env python3

# Copyright (C) 2017 arcalinea <arcalinea@z.cash>

from zmsg.rpc import Proxy
import time, sys
import argparse, textwrap
from .utils import *

__version__ = "0.1.0"

def main():
    zmsg = Zmsg()
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
        description=textwrap.dedent('''\
                Usage:
            --------------------------------
                sendmsg - send a message in the encrypted memo field of a shielded transaction
                checkmsgs - check the messages in the encrypted memo fields of your z-addresses

                '''))
    parser.add_argument("command", action="store", help="Use command 'sendmsg' or 'checkmsgs' to send and receive messages.")
    parser.add_argument("-sendfrom", action="store", help="Address (zaddr or taddr) to send message from. If none specified, finds taddr with unspent.")
    parser.add_argument("-sendto", action="store", help="Address (zaddr) to send message to.")
    parser.add_argument("-txval", action="store", default=0.0001, help="Specify the amount of ZEC to send with messages.")
    parser.add_argument("-msg", action="store", help="Send a message.")
    parser.add_argument("-minconf", action="store", help="Set a number of minimum confirmations on messages checked (default=1)")
    args = parser.parse_args()
    if args.command == "sendmsg":
        if args.sendto == None or args.msg == None:
            print("\nError: You must include a recipient z-address and message with the command 'sendmsg'.\n")
            print(parser.print_help())
        elif args.sendfrom == None:
            zmsg.send_msg(None, args.sendto, args.txval, args.msg)
        else:
            zmsg.send_msg(args.sendfrom, args.sendto, args.txval, args.msg)
    elif args.command == "checkmsgs":
        if args.minconf == None:
            msgs = zmsg.check_msgs()
        else:
            msgs = zmsg.check_msgs(args.minconf)
        for zaddr in msgs:
            print("\n" + "=" * 80)
            print("Messages received at", zaddr, "\n")
            for msg in msgs[zaddr]:
                print("Time received:", msg['time'], "  Amount:", msg['amount'])
                print("Message:", msg['memo'])
                print('-' * 80)
    elif args.command == "test":
        zmsg.check_msgs()
    else:
        print("Invalid command, please use sendmsg or checkmsgs to send and receive messages.")


class Zmsg(object):
    def __init__(self, network='testnet'):
        self.rpc = Proxy(network=network)

    # checkmsgs
    def received_by_zaddr(self, zaddr, minconf):
        msgs = []
        txs = self.rpc.z_listreceivedbyaddress(zaddr, minconf)
        for tx in txs:
            memo = hex_decode(tx['memo'])
            if memo != None:
                resp = self.rpc.gettransaction(tx['txid'])
                t = time.ctime(resp['time'])
                amount = tx['amount']
                msg = {'time': t, 'amount': amount, 'memo': memo}
                msgs.append(msg)
        return msgs

    def check_msgs(self, minconf=1):
        all_msgs = {}
        zaddrs = self.rpc.z_listaddresses()
        for zaddr in zaddrs:
            msgs = self.received_by_zaddr(zaddr, minconf)
            all_msgs[zaddr] = msgs
        return all_msgs

    # Sendmsg
    def find_unspent_taddr(self, amount):
        unspent = self.rpc.listunspent()
        for tx in unspent:
            if tx['spendable'] == True:
                if tx['amount'] > amount:
                    return tx['address']

    def send_msg(self, sender, receiver, amount, msg):
        # if sender is blank, get a new taddr and send from it.
        if sender == '' or sender == None:
            taddr = self.find_unspent_taddr(amount)
            print("No fromaddress provided, sending from {0}".format(taddr))
            sender = taddr
        amounts = format_amounts(receiver, amount, msg)
        opid = self.rpc.z_sendmany(sender, amounts)
        response_array = self.rpc.z_getoperationstatus([opid])
        status = response_array[0]['status']
        print('Status of sendmsg: {0}. Operation id: {1}'.format(status, opid))
        start_time = time.time()
        sys.stdout.write("Sending message...")
        while status == 'executing':
            sys.stdout.write('.')
            sys.stdout.flush()
            response_array = self.rpc.z_getoperationstatus([opid])
            status = response_array[0]['status']
            if status == 'executing':
                time.sleep(1)
            elif status == 'success':
                print("\nSuccess, message sent! OPID: {0}".format(opid))
            elif status == 'failed':
                print("\nSending message failed. OPID: {0}".format(opid))
                raise Exception(response_array[0]['error'])
            else:
                if time.time() > start_time + 120:
                    result = self.rpc.z_getoperationresult([opid])
                    status = result[0]['status']
                    print("\nSending timed out, operation result is {0}".format(status))
                    break
