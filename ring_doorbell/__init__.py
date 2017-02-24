# coding: utf-8
# vim:sw=4:ts=4:et:
"""Python Ring Doorbell wrapper."""
from datetime import datetime

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

import os
import logging
import requests
import pytz

from ring_doorbell.utils import _locator
from ring_doorbell.const import (
    API_VERSION, API_URI, CHIMES_ENDPOINT, CHIME_VOL_MIN, CHIME_VOL_MAX,
    DEVICES_ENDPOINT, DOORBELLS_ENDPOINT, DOORBELL_VOL_MIN, DOORBELL_VOL_MAX,
    DOORBELL_EXISTING_TYPE, DINGS_ENDPOINT, FILE_EXISTS,
    HEADERS, LINKED_CHIMES_ENDPOINT, LIVE_STREAMING_ENDPOINT,
    NEW_SESSION_ENDPOINT, MSG_BOOLEAN_REQUIRED, MSG_EXISTING_TYPE,
    MSG_GENERIC_FAIL, MSG_VOLUME_OUTBOUNDS,
    NOT_FOUND, URL_DOORBELL_HISTORY, URL_RECORDING,
    POST_DATA, RETRY_TOKEN)

_LOGGER = logging.getLogger(__name__)


class Ring(object):
    """A Python Abstraction object to Ring Door Bell."""

    def __init__(self, username, password, debug=False):
        """Initialize the Ring object."""
        self.features = None
        self.is_connected = None
        self._id = None
        self.token = None
        self.params = None

        self.debug = debug
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.auth = (self.username, self.password)

        self._authenticate()

    def _authenticate(self, attempts=RETRY_TOKEN):
        """Authenticate user against Ring API."""
        url = API_URI + NEW_SESSION_ENDPOINT

        loop = 0
        while loop <= attempts:
            loop += 1
            try:
                req = self.session.post((url), data=POST_DATA, headers=HEADERS)
            except:
                raise

            # if token is expired, refresh credentials and try again
            if req.status_code == 201:
                data = req.json().get('profile')
                self.features = data.get('features')
                self._id = data.get('id')
                self.is_connected = True
                self.token = data.get('authentication_token')
                self.params = {'api_version': API_VERSION,
                               'auth_token': self.token}
                return True

        self.is_connected = False
        req.raise_for_status()

    def query(self,
              url,
              attempts=RETRY_TOKEN,
              method='GET',
              raw=False,
              extra_params=None):
        """Query data from Ring API."""
        if self.debug:
            _LOGGER.debug("Querying %s", url)

        if self.debug and not self.is_connected:
            _LOGGER.debug("Not connected. Refreshing token...")
            self._authenticate()

        response = None
        loop = 0
        while loop <= attempts:
            if self.debug:
                _LOGGER.debug("running query loop %s", loop)

            # allow to override params when necessary
            # and update self.params globally for the next connection
            if extra_params:
                params = self.params
                params.update(extra_params)
            else:
                params = self.params

            loop += 1
            try:
                if method == 'GET':
                    req = self.session.get((url), params=urlencode(params))
                elif method == 'PUT':
                    req = self.session.put((url), params=urlencode(params))
                elif method == 'POST':
                    req = self.session.post((url), params=urlencode(params))

                if self.debug:
                    _LOGGER.debug("_query %s ret %s", loop, req.status_code)
            except:
                raise

            # if token is expired, refresh credentials and try again
            if req.status_code == 401:
                self.is_connected = False
                self._authenticate()
                continue

            if req.status_code == 200 or req.status_code == 204:
                # if raw, return session object otherwise return JSON
                if raw:
                    response = req
                else:
                    if method == 'GET':
                        response = req.json()
                return response
        _LOGGER.debug("%s", MSG_GENERIC_FAIL)
        return None

    @property
    def has_subscription(self):
        """Return if account has subscription."""
        try:
            return self.features.get('subscriptions_enabled')
        except AttributeError:
            return NOT_FOUND

    @property
    def devices(self):
        """Return all devices."""
        devs = {}
        devs['chimes'] = self.chimes
        devs['doorbells'] = self.doorbells
        return devs

    def __devices(self, device_type):
        """Private method to query devices."""
        lst = []
        url = API_URI + DEVICES_ENDPOINT
        try:
            if device_type == 'chime':
                req = self.query(url).get('chimes')
                for member in list((obj['description'] for obj in req)):
                    lst.append(RingChime(self, member))

            if device_type == 'doorbell':
                req = self.query(url).get('doorbots')
                for member in list((obj['description'] for obj in req)):
                    lst.append(RingDoorBell(self, member))

        except AttributeError:
            pass
        return lst

    @property
    def chimes(self):
        """Return a list of RingDoorChime objects."""
        return self.__devices('chime')

    @property
    def doorbells(self):
        """Return a list of RingDoorBell objects."""
        return self.__devices('doorbell')


class RingGeneric(object):
    """Generic Implementation for Ring Chime/Doorbell."""

    def __init__(self):
        """Initialize Ring Generic."""
        self._attrs = None
        self.debug = None
        self.family = None
        self.name = None

    def __repr__(self):
        """Return __repr__."""
        return "<{0}: {1}>".format(self.__class__.__name__, self.name)

    def update(self):
        """Refresh attributes."""
        self._get_attrs()

    def _get_attrs(self):
        """Return chime attributes."""
        url = API_URI + DEVICES_ENDPOINT
        try:
            lst = self._ring.query(url).get(self.family)
            index = _locator(lst, 'description', self.name)
            if index == NOT_FOUND:
                return None
        except AttributeError:
            return None

        self._attrs = lst[index]
        return True

    @property
    def account_id(self):
        """Return account ID."""
        return self._attrs.get('id')

    @property
    def address(self):
        """Return address."""
        return self._attrs.get('address')

    @property
    def firmware(self):
        """Return firmware."""
        return self._attrs.get('firmware_version')

    # pylint: disable=invalid-name
    @property
    def id(self):
        """Return ID."""
        return self._attrs.get('device_id')

    @property
    def latitude(self):
        """Return latitude attr."""
        return self._attrs.get('latitude')

    @property
    def longitude(self):
        """Return longitude attr."""
        return self._attrs.get('longitude')

    @property
    def kind(self):
        """Return kind attr."""
        return self._attrs.get('kind')

    @property
    def timezone(self):
        """Return timezone."""
        return self._attrs.get('time_zone')


class RingChime(RingGeneric):
    """Implementation for Ring Chime."""

    def __init__(self, ring, name):
        """Initilize Ring chime object."""
        super(RingChime, self).__init__()
        self._attrs = None
        self._ring = ring
        self.debug = self._ring.debug
        self.family = 'chimes'
        self.name = name
        self.update()

    @property
    def volume(self):
        """Return if chime volume."""
        return self._attrs.get('settings').get('volume')

    @volume.setter
    def volume(self, value):
        if not ((isinstance(value, int)) and
                (value >= CHIME_VOL_MIN and value <= CHIME_VOL_MAX)):
            _LOGGER.error("%s", MSG_VOLUME_OUTBOUNDS.format(CHIME_VOL_MIN,
                                                            CHIME_VOL_MAX))
            return False

        params = {
            'chime[description]': self.name,
            'chime[settings][volume]': str(value)}

        url = API_URI + CHIMES_ENDPOINT.format(self.account_id)
        self._ring.query(url, extra_params=params, method='PUT')
        self.update()
        return True

    @property
    def subscribed(self):
        """Return if chime is online."""
        result = self._attrs.get('firmware_version')
        if result is None:
            return False
        return True

    @property
    def subscribed_motions(self):
        """Return if chime is subscribed_motions."""
        result = self._attrs.get('subscribed_motions')
        if result is None:
            return False
        return True

    @property
    def linked_tree(self):
        """Return doorbell data linked to chime."""
        url = API_URI + LINKED_CHIMES_ENDPOINT.format(self.account_id)
        return self._ring.query(url)


class RingDoorBell(RingGeneric):
    """Implementation for Ring Doorbell."""

    def __init__(self, ring, name):
        """Initilize Ring doorbell object."""
        super(RingDoorBell, self).__init__()
        self._attrs = None
        self._ring = ring
        self.debug = self._ring.debug
        self.family = 'doorbots'
        self.name = name
        self.update()

    @property
    def battery_life(self):
        """Return battery life."""
        value = int(self._attrs.get('battery_life'))
        if value > 100:
            value = 100
        return value

    @property
    def check_activity(self):
        """Return JSON when motion or ring is detected."""
        url = API_URI + DINGS_ENDPOINT
        return self._ring.query(url)

    @property
    def existing_doorbell_type(self):
        """
        Return existing doorbell type.

        0: Mechanical
        1: Digital
        2: Not Present
        """
        return DOORBELL_EXISTING_TYPE[
            self._attrs.get('settings').get('chime_settings').get('type')]

    @existing_doorbell_type.setter
    def existing_doorbell_type(self, value):
        """
        Return existing doorbell type.

        0: Mechanical
        1: Digital
        2: Not Present
        """
        if value not in DOORBELL_EXISTING_TYPE.keys():
            _LOGGER.error("%s", MSG_EXISTING_TYPE)
            return False
        params = {
            'doorbot[description]': self.name,
            'doorbot[settings][chime_settings][type]': value}

        url = API_URI + DOORBELLS_ENDPOINT.format(self.account_id)
        self._ring.query(url, extra_params=params, method='PUT')
        self.update()
        return True

    @property
    def existing_doorbell_type_enabled(self):
        """Return if existing doorbell type is enabled."""
        if self._attrs.get('settings').get('chime_settings').get('type') == 2:
            return False
        return self._attrs.get('settings').get('chime_settings').get('enable')

    @existing_doorbell_type_enabled.setter
    def existing_doorbell_type_enabled(self, value):
        """Enable/disable the existing doorbell if Digital/Mechanical."""
        if self._attrs.get('settings').\
           get('chime_settings').get('type') == 2:
            return False
        if not isinstance(value, bool):
            _LOGGER.error("%s", MSG_BOOLEAN_REQUIRED)
            return False

        params = {
            'doorbot[description]': self.name,
            'doorbot[settings][chime_settings][enable]': value}

        url = API_URI + DOORBELLS_ENDPOINT.format(self.account_id)
        self._ring.query(url, extra_params=params, method='PUT')
        self.update()
        return True

    @property
    def existing_doorbell_type_duration(self):
        """Return duration for Digital chime."""
        if self._attrs.get('settings').get('chime_settings').get('type') == 1:
            return self._attrs.get('settings').\
                   get('chime_settings').get('duration')
        return None

    @existing_doorbell_type_duration.setter
    def existing_doorbell_type_duration(self, value):
        """Set duration for Digital chime."""
        if not ((isinstance(value, int)) and
                (value >= DOORBELL_VOL_MIN and value <= DOORBELL_VOL_MAX)):
            _LOGGER.error("%s", MSG_VOLUME_OUTBOUNDS.format(DOORBELL_VOL_MIN,
                                                            DOORBELL_VOL_MAX))
            return False

        if self._attrs.get('settings').get('chime_settings').get('type') != 1:
            return None

        params = {
            'doorbot[description]': self.name,
            'doorbot[settings][chime_settings][duration]': value}

        url = API_URI + DOORBELLS_ENDPOINT.format(self.account_id)
        self._ring.query(url, extra_params=params, method='PUT')
        self.update()
        return True

    def history(self, limit=30, timezone=None):
        """Return history with datetime objects."""
        # allow modify the items to return
        params = {'limit': str(limit)}

        url = API_URI + URL_DOORBELL_HISTORY.format(self.account_id)
        response = self._ring.query(url, extra_params=params)

        # convert for specific timezone
        utc = pytz.utc
        if timezone:
            mytz = pytz.timezone(timezone)

        for entry in response:
            dt_at = datetime.strptime(entry['created_at'],
                                      '%Y-%m-%dT%H:%M:%S.000Z')
            utc_dt = datetime(dt_at.year, dt_at.month, dt_at.day, dt_at.hour,
                              dt_at.minute, dt_at.second, tzinfo=utc)
            if timezone:
                tz_dt = utc_dt.astimezone(mytz)
                entry['created_at'] = tz_dt
            else:
                entry['created_at'] = utc_dt
        return response

    @property
    def last_recording_id(self):
        """Return the last recording ID."""
        return self.history(limit=1)[0]['id']

    @property
    def live_streaming_json(self):
        """Return JSON for live streaming."""
        url = API_URI + LIVE_STREAMING_ENDPOINT.format(self.account_id)
        req = self._ring.query((url), method='POST', raw=True)
        if req.status_code == 204:
            url = API_URI + DINGS_ENDPOINT
            return self._ring.query(url)[0]
        return None

    def recording_download(self, recording_id, filename=None, override=False):
        """Save a recording in MP4 format to a file or return raw."""
        url = API_URI + URL_RECORDING.format(recording_id)
        try:
            req = self._ring.query(url, raw=True)
            if req.status_code == 200:

                if filename:
                    if os.path.isfile(filename) and not override:
                        _LOGGER.error("%s", FILE_EXISTS.format(filename))
                        return False

                    with open(filename, 'wb') as recording:
                        recording.write(req.content)
                        return True
                else:
                    return req.content
        except IOError as error:
            _LOGGER.error("%s", error)
            raise

    def recording_url(self, recording_id):
        """Return HTTPS recording URL."""
        url = API_URI + URL_RECORDING.format(recording_id)
        req = self._ring.query(url, raw=True)
        if req.status_code == 200:
            return req.url
        return False

    @property
    def volume(self):
        """Return volume."""
        return self._attrs.get('settings').get('doorbell_volume')

    @volume.setter
    def volume(self, value):
        if not ((isinstance(value, int)) and
                (value >= DOORBELL_VOL_MIN and value <= DOORBELL_VOL_MAX)):
            _LOGGER.error("%s", MSG_VOLUME_OUTBOUNDS.format(DOORBELL_VOL_MIN,
                                                            DOORBELL_VOL_MAX))
            return False

        params = {
            'doorbot[description]': self.name,
            'doorbot[settings][doorbell_volume]': str(value)}

        url = API_URI + DOORBELLS_ENDPOINT.format(self.account_id)
        self._ring.query(url, extra_params=params, method='PUT')
        self.update()
        return True
