import argparse
import socket
import sys
from itertools import count
import upnpy


class Igd:
    def __init__(
        self,
        ssdp_st="urn:schemas-upnp-org:device:InternetGatewayDevice:2",
        ssdp_delay=4,
        upnp_service="WANIPConnection",
    ):
        self.local_ip = self._get_local_ip()
        self.service = self._get_upnp_service(
            ssdp_st, ssdp_delay, upnp_service, bind_ip=self.local_ip
        )
        if not self.service:
            raise IgdError("No gateway service found")

    @staticmethod
    def _get_upnp_service(ssdp_st, ssdp_delay, upnp_service, bind_ip=None):
        service_urn = "urn:schemas-upnp-org:service:{}".format(upnp_service)
        ssdp = upnpy.ssdp.SSDPRequest.SSDPRequest(bind_ip=bind_ip)
        for device in ssdp.m_search(discover_delay=ssdp_delay, st=ssdp_st):
            for service in device.get_services():
                if service.service.startswith(service_urn):
                    return service
        return None

    @staticmethod
    def _get_local_ip():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except:
            return None
        finally:
            sock.close()

    def AddPortMapping(self, port, protocol, description):
        try:
            self.service.AddPortMapping(
                NewRemoteHost="",
                NewExternalPort=port,
                NewProtocol=protocol,
                NewInternalPort=port,
                NewInternalClient=self.local_ip,
                NewEnabled=1,
                NewPortMappingDescription=description,
                NewLeaseDuration=0,
            )
        except upnpy.exceptions.SOAPError as e:
            raise IgdError(
                "Failed to add mapping for {} port {}, "
                "error {}: {}".format(protocol, port, e.error, e.description)
            )

    def DeletePortMapping(self, port, protocol):
        try:
            self.service.DeletePortMapping(
                NewRemoteHost="", NewExternalPort=port, NewProtocol=protocol
            )
        except upnpy.exceptions.SOAPError as e:
            raise IgdError(
                "Failed to delete mapping for {} port {}, "
                "error {}: {}".format(protocol, port, e.error, e.description)
            )

    def GetPortMappings(self):
        mappings = []
        for i in count():
            try:
                mappings.append(
                    self.service.GetGenericPortMappingEntry(NewPortMappingIndex=i)
                )
            except:
                break
        return mappings

    def HasPortMapping(self, port, protocol):
        for mapping in self.GetPortMappings():
            if (
                mapping["NewExternalPort"] == str(port)
                and mapping["NewProtocol"] == protocol
            ):
                return True
        return False


class IgdError(Exception):
    def __init__(self, message):
        self.message = message


def _discover(_):
    igd = Igd()
    print("Gateway service found, description: {}".format(igd.service.scpd_url))


def _add(args):
    port = args.port
    protocol = args.protocol.upper()
    description = " ".join(args.description)

    igd = Igd()
    if not igd.HasPortMapping(port, protocol):
        igd.AddPortMapping(port, protocol, description)
        print("Mapping for {} port {} added".format(protocol, port))


def _delete(args):
    port = args.port
    protocol = args.protocol.upper()

    igd = Igd()
    igd.DeletePortMapping(port, protocol)
    print("Mapping for {} port {} deleted".format(protocol, port))


def _list(_):
    igd = Igd()
    for mapping in igd.GetPortMappings():
        print(
            "{:>5}  {}  {:15} {:5}  {:37}  {:>5}s".format(
                mapping["NewExternalPort"],
                mapping["NewProtocol"],
                mapping["NewInternalClient"],
                mapping["NewInternalPort"],
                mapping["NewPortMappingDescription"],
                mapping["NewLeaseDuration"],
            )
        )


def main():
    parser = argparse.ArgumentParser(prog="igd")
    subparsers = parser.add_subparsers(title="commands", required=True)
    parser_discover = subparsers.add_parser("discover", help="discover gateway")
    parser_discover.set_defaults(func=_discover)
    parser_add = subparsers.add_parser("add", help="add port mapping")
    parser_add.set_defaults(func=_add)
    parser_add.add_argument("port", type=int)
    parser_add.add_argument("protocol", choices=["tcp", "udp"], type=str.lower)
    parser_add.add_argument("description", type=str, default="", nargs="*")
    parser_delete = subparsers.add_parser("delete", help="delete port mapping")
    parser_delete.add_argument("port", type=int)
    parser_delete.add_argument("protocol", choices=["tcp", "udp"], type=str.lower)
    parser_delete.set_defaults(func=_delete)
    parser_list = subparsers.add_parser("list", help="list port mappings")
    parser_list.set_defaults(func=_list)

    args = parser.parse_args()
    try:
        args.func(args)
    except IgdError as e:
        sys.exit(e.message)


if __name__ == "__main__":
    main()
