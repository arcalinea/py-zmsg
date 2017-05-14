# Copyright (C) 2007 Jan-Klaas Kollhof
# Copyright (C) 2011-2015 The python-bitcoinlib developers
# Copyright (C) 2017 arcalinea <arcalinea@z.cash>

try:
    import http.client as httplib
except ImportError:
    import httplib
import base64
import binascii
import decimal
import json
import os
import platform
import sys
try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse

DEFAULT_USER_AGENT = "AuthServiceProxy/0.1"

DEFAULT_HTTP_TIMEOUT = 30

class JSONRPCError(Exception):
    """JSON-RPC protocol error base class

    Subclasses of this class also exist for specific types of errors; the set
    of all subclasses is by no means complete.
    """

    SUBCLS_BY_CODE = {}

    @classmethod
    def _register_subcls(cls, subcls):
        cls.SUBCLS_BY_CODE[subcls.RPC_ERROR_CODE] = subcls
        return subcls

    def __new__(cls, rpc_error):
        assert cls is JSONRPCError
        cls = JSONRPCError.SUBCLS_BY_CODE.get(rpc_error['code'], cls)

        self = Exception.__new__(cls)

        super(JSONRPCError, self).__init__(
            'msg: %r  code: %r' %
            (rpc_error['message'], rpc_error['code']))
        self.error = rpc_error

        return self

@JSONRPCError._register_subcls
class ForbiddenBySafeModeError(JSONRPCError):
    RPC_ERROR_CODE = -2

@JSONRPCError._register_subcls
class InvalidAddressOrKeyError(JSONRPCError):
    RPC_ERROR_CODE = -5

@JSONRPCError._register_subcls
class InvalidParameterError(JSONRPCError):
    RPC_ERROR_CODE = -8

@JSONRPCError._register_subcls
class VerifyError(JSONRPCError):
    RPC_ERROR_CODE = -25

@JSONRPCError._register_subcls
class VerifyRejectedError(JSONRPCError):
    RPC_ERROR_CODE = -26

@JSONRPCError._register_subcls
class VerifyAlreadyInChainError(JSONRPCError):
    RPC_ERROR_CODE = -27

@JSONRPCError._register_subcls
class InWarmupError(JSONRPCError):
    RPC_ERROR_CODE = -28

class BaseProxy(object):
    """Base JSON-RPC proxy class. Contains only private methods; do not use
    directly."""

    def __init__(self, network=None,
                 service_url=None,
                 service_port=None,
                 zcash_conf_file=None,
                 timeout=DEFAULT_HTTP_TIMEOUT):

        # Create a dummy connection early on so if __init__() fails prior to
        # __conn being created __del__() can detect the condition and handle it
        # correctly.
        self.__conn = None

        # Set ports for networks
        if network == 'testnet':
            service_port = 18232
        elif network == 'mainnet':
            service_port = 8232
        else:
            raise Exception("Please specify network='testnet' or 'mainnet'")

        if service_url is None:
            # Figure out the path to the zcash.conf file
            if zcash_conf_file is None:
                if platform.system() == 'Windows':
                    zcash_conf_file = os.path.join(os.environ['APPDATA'], 'Zcash')
                else:
                    zcash_conf_file = os.path.expanduser('~/.zcash')
                zcash_conf_file = os.path.join(zcash_conf_file, 'zcash.conf')

            # Extract contents of zcash.conf to build service_url
            with open(zcash_conf_file, 'r') as fd:
                # zcash accepts empty rpcuser, not specified in zcash_conf_file
                conf = {'rpcuser': ""}
                for line in fd.readlines():
                    if '#' in line:
                        line = line[:line.index('#')]
                    if '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    conf[k.strip()] = v.strip()

                if service_port is None:
                    service_port = network
                conf['rpcport'] = int(conf.get('rpcport', service_port))
                conf['rpchost'] = conf.get('rpcconnect', 'localhost')

                if 'rpcpassword' not in conf:
                    raise ValueError('The value of rpcpassword not specified in the configuration file: %s' % zcash_conf_file)

                service_url = ('%s://%s:%s@%s:%d' %
                    ('http',
                     conf['rpcuser'], conf['rpcpassword'],
                     conf['rpchost'], conf['rpcport']))

        self.__service_url = service_url
        self.__url = urlparse.urlparse(service_url)

        if self.__url.scheme not in ('http',):
            raise ValueError('Unsupported URL scheme %r' % self.__url.scheme)

        if self.__url.port is None:
            port = httplib.HTTP_PORT
        else:
            port = self.__url.port
        self.__id_count = 0
        authpair = "%s:%s" % (self.__url.username, self.__url.password)
        authpair = authpair.encode('utf8')
        self.__auth_header = b"Basic " + base64.b64encode(authpair)

        self.__conn = httplib.HTTPConnection(self.__url.hostname, port=port,
                                             timeout=timeout)


    def _call(self, service_name, *args):
        self.__id_count += 1

        postdata = json.dumps({'version': '1.1',
                               'method': service_name,
                               'params': args,
                               'id': self.__id_count})
        self.__conn.request('POST', self.__url.path, postdata,
                            {'Host': self.__url.hostname,
                             'User-Agent': DEFAULT_USER_AGENT,
                             'Authorization': self.__auth_header,
                             'Content-type': 'application/json'})

        response = self._get_response()
        if response['error'] is not None:
            raise JSONRPCError(response['error'])
        elif 'result' not in response:
            raise JSONRPCError({
                'code': -343, 'message': 'missing JSON-RPC result'})
        else:
            return response['result']


    def _batch(self, rpc_call_list):
        postdata = json.dumps(list(rpc_call_list))
        self.__conn.request('POST', self.__url.path, postdata,
                            {'Host': self.__url.hostname,
                             'User-Agent': DEFAULT_USER_AGENT,
                             'Authorization': self.__auth_header,
                             'Content-type': 'application/json'})

        return self._get_response()

    def _get_response(self):
        http_response = self.__conn.getresponse()
        if http_response is None:
            raise JSONRPCError({
                'code': -342, 'message': 'missing HTTP response from server'})

        return json.loads(http_response.read().decode('utf8'),
                          parse_float=decimal.Decimal)

    def __del__(self):
        if self.__conn is not None:
            self.__conn.close()


class Proxy(BaseProxy):
    """Proxy to a zcash RPC service

    Unlike ``RawProxy``, data is passed as ``zcash.core`` objects or packed
    bytes, rather than JSON or hex strings. Not all methods are implemented
    yet; you can use ``call`` to access missing ones in a forward-compatible
    way. Assumes Zcash version >= v1.0.0
    """

    def __init__(self,
                 service_url=None,
                 service_port=None,
                 zcash_conf_file=None,
                 timeout=DEFAULT_HTTP_TIMEOUT,
                 **kwargs):
        """Create a proxy object

        If ``service_url`` is not specified, the username and password are read
        out of the file ``zcash_conf_file``. If ``zcash_conf_file`` is not
        specified, ``~/.zcash/zcash.conf`` or equivalent is used by
        default.  The default port is set according to the chain parameters in
        use: mainnet, testnet, or regtest.

        Usually no arguments to ``Proxy()`` are needed; the local zcashd will
        be used.

        ``timeout`` - timeout in seconds before the HTTP interface times out
        """

        super(Proxy, self).__init__(service_url=service_url,
                                    service_port=service_port,
                                    zcash_conf_file=zcash_conf_file,
                                    timeout=timeout,
                                    **kwargs)

    def call(self, service_name, *args):
        """Call an RPC method by name and raw (JSON encodable) arguments"""
        return self._call(service_name, *args)

    def gettransaction(self, txid, includeWatchonly=False):
        """Get detailed information about in-wallet transaction txid

        Raises IndexError if transaction not found in the wallet.

        includeWatchonly - Whether to include watchonly addresses in balance calculation and details

        FIXME: Returned data types are not yet converted.
        """
        if type(txid) == str:
            r = self._call('gettransaction', txid)
        else:
            try:
                r = self._call('gettransaction', b2lx(txid))
            except InvalidAddressOrKeyError as ex:
                raise IndexError('%s.getrawtransaction(): %s (%d)' %
                        (self.__class__.__name__, ex.error['message'], ex.error['code']))
        return r

    def listunspent(self, minconf=0, maxconf=9999999, addrs=None):
        """Return unspent transaction outputs in wallet

        Outputs will have between minconf and maxconf (inclusive)
        confirmations, optionally filtered to only include txouts paid to
        addresses in addrs.
        """
        r = None
        if addrs is None:
            r = self._call('listunspent', minconf, maxconf)
        else:
            addrs = [str(addr) for addr in addrs]
            r = self._call('listunspent', minconf, maxconf, addrs)
        return r

    def z_getoperationresult(self, opid):
        """Retrieve the result and status of an operation which has finished, and then remove the operation from memory.
        opid - (array, optional) A list of operation ids we are interested in.
        If not provided, examine all operations known to the node.
        """
        return self._call('z_getoperationresult', opid)

    def z_getoperationstatus(self, opid):
        """Get operation status and any associated result or error data.  The operation will remain in memory.
        opid - (array, optional) A list of operation ids we are interested in.
        If not provided, examine all operations known to the node.
        """
        return self._call('z_getoperationstatus', opid)


    def z_listreceivedbyaddress(self, zaddr, minconf=1):
        """Return a list of amounts received by a zaddr belonging to the node’s wallet."""
        r = self._call('z_listreceivedbyaddress', str(zaddr), minconf)
        return r

    def z_listaddresses(self):
        """Returns the list of zaddr belonging to the wallet."""
        return self._call('z_listaddresses')

    def z_sendmany(self, fromaddress, amounts, minconf=1, fee=0.0001):
        """Send multiple times. Amounts are double-precision floating point numbers.
        Change from a taddr flows to a new taddr address, while change from zaddr returns to itself.
        When sending coinbase UTXOs to a zaddr, change is not allowed. The entire value of the UTXO(s) must be consumed.
        Currently, the maximum number of zaddr outputs is 54 due to transaction size limits.
        1. "fromaddress"         (string, required) The taddr or zaddr to send the funds from.
        2. "amounts"             (array, required) An array of json objects representing the amounts to send.
            [{
              "address":address  (string, required) The address is a taddr or zaddr
              "amount":amount    (numeric, required) The numeric amount in ZEC is the value
              "memo":memo        (string, optional) If the address is a zaddr, raw data represented in hexadecimal string format
            }, ... ]
        3. minconf               (numeric, optional, default=1) Only use funds confirmed at least this many times.
        4. fee                   (numeric, optional, default=0.0001) The fee amount to attach to this transaction.
        """
        fromaddress = str(fromaddress)
        r = self._call('z_sendmany', fromaddress, amounts, minconf, fee)
        return r
