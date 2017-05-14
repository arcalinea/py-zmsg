import binascii

COIN = 100000000


def hex_decode(msg):
    msgstr = msg.rstrip('0')
    if msgstr != 'f6':
        decoded = binascii.unhexlify(msgstr).decode('ascii')
        return decoded

def format_amounts(receiver, amount, msg):
    amts_array = []
    if msg == '':
        amounts = {"address": receiver, "amount": amount}
    else:
        memo = str(binascii.b2a_hex(bytes(msg, encoding="ascii")), 'ascii')
        amounts = {"address": receiver, "amount": amount, "memo": memo}
    amts_array.append(amounts)
    return amts_array
