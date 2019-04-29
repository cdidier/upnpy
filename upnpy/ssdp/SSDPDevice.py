from urllib.parse import urlparse
from xml.dom import minidom
from functools import wraps

import upnpy.utils as utils
from upnpy.soap import SOAP


def _device_description_required(func):

    """
    Decorator for checking whether the device description is available on a device.
    """

    @wraps(func)
    def wrapper(device, *args, **kwargs):
        if device.description is None:
            raise ValueError('No device description retrieved for this device.')
        return func(device, *args, **kwargs)
    return wrapper


def _service_description_required(func):

    """
    Decorator for checking whether the service description is available on a device's service.
    """

    @wraps(func)
    def wrapper(service, *args, **kwargs):
        if service.description is None:
            raise ValueError('No service description retrieved for this service.')
        return func(service, *args, **kwargs)
    return wrapper


def _base_url_required(func):

    """
    Decorator for constructing the BaseURL (from device response LOCATION header
    or <URLBase> element in device description).
    """

    @wraps(func)
    def wrapper(instance, *args, **kwargs):
        if instance.base_url is None:
            raise ValueError('No base URL was retrieved for this device.')
        return func(instance, *args, **kwargs)
    return wrapper


class SSDPDevice:

    """
        **Represents an SSDP device**

        Object for representing an SSDP device.

        :param address: SSDP device address
        :type address: tuple
        :param response: Device discovery response data
        :type response: str
    """

    def __init__(self, address, response):
        self.address = address
        self.host = address[0]
        self.port = address[1]
        self.response = response
        self.description = None
        self.type_ = None
        self.base_url = None
        self.services = {}
        self.selected_service = None

        self._get_description(utils.parse_http_header(response, 'Location'))
        self._get_type()
        self._get_base_url()
        self._get_services()

    def _get_description(self, url):
        device_description = utils.make_http_request(url).read()
        self.description = device_description
        return device_description.decode()

    @_device_description_required
    def _get_type(self):
        root = minidom.parseString(self.description)
        device_type = root.getElementsByTagName('deviceType')[0].firstChild.nodeValue
        print('Device type', device_type)
        self.type_ = device_type
        return self.type_

    @_device_description_required
    def _get_base_url(self):
        location_header_value = utils.parse_http_header(self.response, 'Location')
        root = minidom.parseString(self.description)

        try:
            parsed_url = urlparse(root.getElementsByTagName('URLBase')[0].firstChild.nodeValue)
            base_url = f'{parsed_url.scheme}://{parsed_url.netloc}'
        except IndexError:
            parsed_url = urlparse(location_header_value)
            base_url = f'{parsed_url.scheme}://{parsed_url.netloc}'

        self.base_url = base_url
        return base_url

    @_device_description_required
    @_base_url_required
    def _get_services(self):
        if not self.services:
            device_services = {}
            root = minidom.parseString(self.description)

            base_url = self.base_url

            for service in root.getElementsByTagName('service'):
                service_string = service.getElementsByTagName('serviceType')[0].firstChild.nodeValue
                service_id = service.getElementsByTagName('serviceId')[0].firstChild.nodeValue
                scpd_url = service.getElementsByTagName('SCPDURL')[0].firstChild.nodeValue
                control_url = service.getElementsByTagName('controlURL')[0].firstChild.nodeValue
                event_sub_url = service.getElementsByTagName('eventSubURL')[0].firstChild.nodeValue

                parsed_service_id = utils.parse_service_id(service_id)

                if parsed_service_id not in device_services.keys():
                    device_services[parsed_service_id] = self.Service(
                        service=service_string,
                        service_id=service_id,
                        scpd_url=scpd_url,
                        control_url=control_url,
                        event_sub_url=event_sub_url,
                        base_url=base_url
                    )

            self.services = device_services

        return self.services

    class Service:

        """
            **Device service**

            Represents a service available on the device.

            :param service: Full service string (e.g.: ``urn:schemas-upnp-org:service:WANIPConnection:1``)
            :type service: str
            :param service_id: ID of the service
            :type service_id: str
            :param scpd_url: SCPD URL of the service
            :type scpd_url: str
            :param control_url: Control URL of the service
            :type control_url: str
            :param event_sub_url: Event Sub URL of the service
            :type event_sub_url: str
            :param base_url: Base URL of the service
            :type base_url: str
        """

        def __init__(self, service, service_id, scpd_url, control_url, event_sub_url, base_url):
            self.service = service
            self.type_ = self._get_service_type(service)
            self.version = self._get_service_version(service)
            self.id = service_id
            self.scpd_url = scpd_url
            self.control_url = control_url
            self.event_sub_url = event_sub_url
            self.base_url = base_url
            self.actions = []
            self.description = None

            self._get_description()
            self._get_actions()

        def _get_description(self):

            """
                **Get the description of the service**

                Gets the service description by sending a request to the SCPD URL of the service.

                :return: Service description
                :rtype: str
            """

            service_description = utils.make_http_request(self.base_url + self.scpd_url).read()
            self.description = service_description.decode()
            return self.description

        @_service_description_required
        def _get_actions(self):

            """
                **Get the service actions**

                Gets the actions available for the service.

                :return: List of actions available for the service
                :rtype: list
            """

            all_actions = {}
            service_description = self.description

            root = minidom.parseString(service_description)
            actions = root.getElementsByTagName('action')

            for action in actions:
                action_name = action.getElementsByTagName('name')[0].firstChild.nodeValue
                action_arguments = []

                # An action's argument list is only required if the action has parameters according to UPnP spec
                try:
                    action_argument_list = action.getElementsByTagName('argumentList')[0]
                except IndexError:
                    action_argument_list = None

                if action_argument_list:
                    action_arguments_elements = action_argument_list.getElementsByTagName('argument')

                    for argument in action_arguments_elements:
                        argument_name = argument.getElementsByTagName('name')[0].firstChild.nodeValue
                        argument_direction = argument.getElementsByTagName('direction')[0].firstChild.nodeValue

                        # Argument return value is optional according to UPnP spec
                        try:
                            argument_return_value = argument.getElementsByTagName('retval')[0].firstChild.nodeValue
                        except IndexError:
                            argument_return_value = None

                        argument_related_state_variable = argument.getElementsByTagName(
                            'relatedStateVariable'
                        )[0].firstChild.nodeValue

                        action_arguments.append(
                            self.Action.Argument(
                                argument_name,
                                argument_direction,
                                argument_return_value,
                                argument_related_state_variable
                            )
                        )

                all_actions[action_name] = self.Action(action_name, action_arguments, self)

            self.actions = all_actions
            return all_actions

        @staticmethod
        def _get_service_type(service):

            """
            Parse the service type <serviceType> portion of the service.
            """

            return service.split(':')[3]

        @staticmethod
        def _get_service_version(service):

            """
            Parse the service version <v> portion of the service.
            """

            return int(service.split(':')[4])

        def __getattr__(self, action_name):

            """
                **Allow executing an action through an attribute**

                Allows executing the specified action on the service through an attribute.

                :param action_name: Name of the action to execute on the service
                :return: Response from the device's service after executing the specified action
                :rtype: dict
            """

            return self.actions[action_name].execute

        class Action:

            """
                **Represents an action on a service**

                This class holds the details of a specific action available on a service.

                :param name: Name of the action
                :type name: str
                :param argument_list: List of in / out arguments the action has
                :type argument_list: list
                :param service: The service to which this action belongs
                :type service: SSDPDevice.Service
            """

            def __init__(self, name, argument_list, service):
                self.name = name
                self.arguments = argument_list
                self.args_in = []
                self.args_out = []
                self.service = service

                for argument in self.arguments:
                    direction = argument.direction
                    if direction == 'in':
                        self.args_in.append(argument)
                    elif direction == 'out':
                        self.args_out.append(argument)
                    else:
                        raise ValueError('No valid argument direction specified by service for'
                                         f' argument "{argument.name}".')

            def execute(self, **action_kwargs):

                """
                    **Execute the action**

                    Executes the action on the service.

                    :param action_kwargs: Arguments for this action if any
                    :type action_kwargs: str, int
                    :return: Response from the device's service after executing the action
                    :rtype: dict
                """

                return SOAP.send(self.service, self, **action_kwargs)

            class Argument:

                """
                    **Represents an argument on for an action**

                    This class holds the details of an argument for an action.

                    :param name: Name of the argument
                    :type name: str
                    :param direction: Direction of the argument (in/out)
                    :type direction: str
                    :param return_value: Identifies at most one output argument as the return value
                    :type return_value: str
                    :param related_state_variable: Defines the type of the argument
                """

                def __init__(self, name, direction, return_value, related_state_variable):
                    self.name = name
                    self.direction = direction
                    self.return_value = return_value
                    self.related_state_variable = related_state_variable
