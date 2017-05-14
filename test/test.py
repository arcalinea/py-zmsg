from zmsg import *

z = Zmsg()
msgs = z.check_msgs()

print("ALL MESSAGES", msgs)
