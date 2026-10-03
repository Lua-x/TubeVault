"""DLNA/UPnP media server: smart TVs, consoles and VLC find the library in the home network.

Two parts: SSDP announces TubeVault in the network (UDP multicast, port 1900) and
answers searches; the HTTP side (app/routers/dlna.py) serves the device description,
the ContentDirectory (Browse) and the files. DLNA knows no logins, so it is off by
default, answers only addresses of the home network and shows what one chosen account
may see.
"""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import random
import socket
import struct
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session, sessionmaker

from app import __version__
from app.models import Setting
from app.services.app_settings import load_app_settings

log = logging.getLogger(__name__)

SSDP_GROUP = "239.255.255.250"
SSDP_PORT = 1900
MAX_AGE = 1800
DEVICE_TYPE = "urn:schemas-upnp-org:device:MediaServer:1"
CONTENT_DIRECTORY = "urn:schemas-upnp-org:service:ContentDirectory:1"
CONNECTION_MANAGER = "urn:schemas-upnp-org:service:ConnectionManager:1"
SERVER_HEADER = f"Linux/1.0 UPnP/1.0 TubeVault/{__version__}"
# DLNA: byte seeking allowed, not converted, streaming.
DLNA_FEATURES = "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"


def is_home_network(host: str | None) -> bool:
    """Private, loopback and link-local addresses – where a TV at home comes from."""
    try:
        address = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def local_ip_for(peer: str) -> str:
    """This machine's address as seen from `peer` (nothing is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect((peer, SSDP_PORT))
            return str(probe.getsockname()[0])
        except OSError:
            return "127.0.0.1"


# --- documents ---------------------------------------------------------------------------

DEVICE_NS = "urn:schemas-upnp-org:device-1-0"


def device_description(name: str, udn: str) -> bytes:
    root = ET.Element("root", {"xmlns": DEVICE_NS})
    spec = ET.SubElement(root, "specVersion")
    ET.SubElement(spec, "major").text = "1"
    ET.SubElement(spec, "minor").text = "0"
    device = ET.SubElement(root, "device")
    for tag, text in (
        ("deviceType", DEVICE_TYPE),
        ("friendlyName", name),
        ("manufacturer", "TubeVault"),
        ("manufacturerURL", "https://github.com/Lua-x/TubeVault"),
        ("modelName", "TubeVault"),
        ("modelNumber", __version__),
        ("UDN", udn),
    ):
        ET.SubElement(device, tag).text = text
    dlna = ET.SubElement(device, "{urn:schemas-dlna-org:device-1-0}X_DLNADOC")
    dlna.text = "DMS-1.50"
    icons = ET.SubElement(device, "iconList")
    icon = ET.SubElement(icons, "icon")
    for tag, text in (
        ("mimetype", "image/png"),
        ("width", "192"),
        ("height", "192"),
        ("depth", "24"),
        ("url", "/dlna/icon.png"),
    ):
        ET.SubElement(icon, tag).text = text
    services = ET.SubElement(device, "serviceList")
    for kind, short in (
        (CONTENT_DIRECTORY, "ContentDirectory"),
        (CONNECTION_MANAGER, "ConnectionManager"),
    ):
        service = ET.SubElement(services, "service")
        ET.SubElement(service, "serviceType").text = kind
        ET.SubElement(service, "serviceId").text = f"urn:upnp-org:serviceId:{short}"
        ET.SubElement(service, "SCPDURL").text = f"/dlna/{short}.xml"
        ET.SubElement(service, "controlURL").text = f"/dlna/control/{short}"
        ET.SubElement(service, "eventSubURL").text = f"/dlna/event/{short}"
    ET.register_namespace("dlna", "urn:schemas-dlna-org:device-1-0")
    return bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _scpd(
    actions: dict[str, list[tuple[str, str, str]]], variables: list[tuple[str, str]]
) -> bytes:
    """Service description: actions with (argument, direction, related variable)."""
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<scpd xmlns="urn:schemas-upnp-org:service-1-0">',
    ]
    parts.append("<specVersion><major>1</major><minor>0</minor></specVersion><actionList>")
    for action, arguments in actions.items():
        parts.append(f"<action><name>{action}</name><argumentList>")
        for argument, direction, variable in arguments:
            parts.append(
                f"<argument><name>{argument}</name><direction>{direction}</direction>"
                f"<relatedStateVariable>{variable}</relatedStateVariable></argument>"
            )
        parts.append("</argumentList></action>")
    parts.append("</actionList><serviceStateTable>")
    for variable, data_type in variables:
        events = "yes" if variable == "SystemUpdateID" else "no"
        parts.append(
            f'<stateVariable sendEvents="{events}"><name>{variable}</name>'
            f"<dataType>{data_type}</dataType></stateVariable>"
        )
    parts.append("</serviceStateTable></scpd>")
    return "".join(parts).encode()


CONTENT_DIRECTORY_SCPD = _scpd(
    {
        "Browse": [
            ("ObjectID", "in", "A_ARG_TYPE_ObjectID"),
            ("BrowseFlag", "in", "A_ARG_TYPE_BrowseFlag"),
            ("Filter", "in", "A_ARG_TYPE_Filter"),
            ("StartingIndex", "in", "A_ARG_TYPE_Index"),
            ("RequestedCount", "in", "A_ARG_TYPE_Count"),
            ("SortCriteria", "in", "A_ARG_TYPE_SortCriteria"),
            ("Result", "out", "A_ARG_TYPE_Result"),
            ("NumberReturned", "out", "A_ARG_TYPE_Count"),
            ("TotalMatches", "out", "A_ARG_TYPE_Count"),
            ("UpdateID", "out", "A_ARG_TYPE_UpdateID"),
        ],
        "GetSearchCapabilities": [("SearchCaps", "out", "SearchCapabilities")],
        "GetSortCapabilities": [("SortCaps", "out", "SortCapabilities")],
        "GetSystemUpdateID": [("Id", "out", "SystemUpdateID")],
    },
    [
        ("A_ARG_TYPE_ObjectID", "string"),
        ("A_ARG_TYPE_BrowseFlag", "string"),
        ("A_ARG_TYPE_Filter", "string"),
        ("A_ARG_TYPE_Index", "ui4"),
        ("A_ARG_TYPE_Count", "ui4"),
        ("A_ARG_TYPE_SortCriteria", "string"),
        ("A_ARG_TYPE_Result", "string"),
        ("A_ARG_TYPE_UpdateID", "ui4"),
        ("SearchCapabilities", "string"),
        ("SortCapabilities", "string"),
        ("SystemUpdateID", "ui4"),
    ],
)

CONNECTION_MANAGER_SCPD = _scpd(
    {
        "GetProtocolInfo": [
            ("Source", "out", "SourceProtocolInfo"),
            ("Sink", "out", "SinkProtocolInfo"),
        ],
        "GetCurrentConnectionIDs": [("ConnectionIDs", "out", "CurrentConnectionIDs")],
    },
    [
        ("SourceProtocolInfo", "string"),
        ("SinkProtocolInfo", "string"),
        ("CurrentConnectionIDs", "string"),
    ],
)


# --- SOAP --------------------------------------------------------------------------------


def parse_soap(body: bytes) -> tuple[str, dict[str, str]]:
    """(action, arguments) of a SOAP request; namespaces are ignored."""
    root = ET.fromstring(body)  # noqa: S314 – small request from the home network, no DTDs
    envelope_body = next((el for el in root if el.tag.endswith("Body")), None)
    if envelope_body is None or len(envelope_body) == 0:
        raise ValueError("Kein SOAP-Body")
    call = envelope_body[0]
    action = call.tag.rsplit("}", 1)[-1]
    arguments = {child.tag.rsplit("}", 1)[-1]: (child.text or "") for child in call}
    return action, arguments


def soap_response(service: str, action: str, values: dict[str, str]) -> bytes:
    inner = "".join(f"<{key}>{escape(value)}</{key}>" for key, value in values.items())
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
        f'<u:{action}Response xmlns:u="{service}">{inner}</u:{action}Response>'
        "</s:Body></s:Envelope>"
    ).encode()


def soap_fault(code: int, description: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><s:Fault>'
        "<faultcode>s:Client</faultcode><faultstring>UPnPError</faultstring><detail>"
        f'<UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>{code}</errorCode>'
        f"<errorDescription>{escape(description)}</errorDescription></UPnPError>"
        "</detail></s:Fault></s:Body></s:Envelope>"
    ).encode()


# --- DIDL-Lite ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Container:
    id: str
    parent: str
    title: str
    child_count: int


@dataclass(frozen=True)
class Item:
    id: str
    parent: str
    title: str
    url: str
    mime: str
    size: int | None = None
    duration_s: int | None = None
    width: int | None = None
    height: int | None = None
    published: date | None = None
    creator: str | None = None
    thumbnail: str | None = None


def _duration(seconds: int) -> str:
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}.000"


def didl(entries: list[Container | Item]) -> str:
    parts = [
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
        'xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/">'
    ]
    for entry in entries:
        if isinstance(entry, Container):
            parts.append(
                f'<container id="{escape(entry.id)}" parentID="{escape(entry.parent)}" '
                f'restricted="1" childCount="{entry.child_count}">'
                f"<dc:title>{escape(entry.title)}</dc:title>"
                "<upnp:class>object.container.storageFolder</upnp:class></container>"
            )
            continue
        attributes = [f'protocolInfo="http-get:*:{entry.mime}:{DLNA_FEATURES}"']
        if entry.size:
            attributes.append(f'size="{entry.size}"')
        if entry.duration_s:
            attributes.append(f'duration="{_duration(entry.duration_s)}"')
        if entry.width and entry.height:
            attributes.append(f'resolution="{entry.width}x{entry.height}"')
        parts.append(
            f'<item id="{escape(entry.id)}" parentID="{escape(entry.parent)}" restricted="1">'
            f"<dc:title>{escape(entry.title)}</dc:title>"
            "<upnp:class>object.item.videoItem</upnp:class>"
        )
        if entry.published:
            parts.append(f"<dc:date>{entry.published.isoformat()}</dc:date>")
        if entry.creator:
            parts.append(f"<dc:creator>{escape(entry.creator)}</dc:creator>")
        if entry.thumbnail:
            parts.append(
                '<upnp:albumArtURI dlna:profileID="JPEG_TN">'
                f"{escape(entry.thumbnail)}</upnp:albumArtURI>"
            )
        parts.append(f"<res {' '.join(attributes)}>{escape(entry.url)}</res></item>")
    parts.append("</DIDL-Lite>")
    return "".join(parts)


# --- SSDP --------------------------------------------------------------------------------


def _targets(udn: str) -> list[tuple[str, str]]:
    """(NT/ST, USN) pairs this device answers for."""
    return [
        ("upnp:rootdevice", f"{udn}::upnp:rootdevice"),
        (udn, udn),
        (DEVICE_TYPE, f"{udn}::{DEVICE_TYPE}"),
        (CONTENT_DIRECTORY, f"{udn}::{CONTENT_DIRECTORY}"),
        (CONNECTION_MANAGER, f"{udn}::{CONNECTION_MANAGER}"),
    ]


def search_responses(request: bytes, udn: str, location: str) -> list[bytes]:
    """Unicast answers to an M-SEARCH, or none if it isn't one or not for us."""
    try:
        text = request.decode("utf-8", "replace")
    except UnicodeDecodeError:  # pragma: no cover – "replace" never raises
        return []
    lines = text.split("\r\n")
    if not lines or not lines[0].upper().startswith("M-SEARCH"):
        return []
    headers = {}
    for line in lines[1:]:
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip().lower()] = value.strip()
    if headers.get("man", "").strip('"') != "ssdp:discover":
        return []
    wanted = headers.get("st", "")
    answers = []
    for target, usn in _targets(udn):
        if wanted in ("ssdp:all", target):
            answers.append(
                (
                    "HTTP/1.1 200 OK\r\n"
                    f"CACHE-CONTROL: max-age={MAX_AGE}\r\n"
                    "EXT:\r\n"
                    f"LOCATION: {location}\r\n"
                    f"SERVER: {SERVER_HEADER}\r\n"
                    f"ST: {target}\r\n"
                    f"USN: {usn}\r\n"
                    "\r\n"
                ).encode()
            )
    return answers


def notify_messages(udn: str, location: str, alive: bool) -> list[bytes]:
    kind = "ssdp:alive" if alive else "ssdp:byebye"
    messages = []
    for target, usn in _targets(udn):
        lines = [
            "NOTIFY * HTTP/1.1",
            f"HOST: {SSDP_GROUP}:{SSDP_PORT}",
            f"NT: {target}",
            f"NTS: {kind}",
            f"USN: {usn}",
        ]
        if alive:
            lines += [
                f"CACHE-CONTROL: max-age={MAX_AGE}",
                f"LOCATION: {location}",
                f"SERVER: {SERVER_HEADER}",
            ]
        messages.append(("\r\n".join(lines) + "\r\n\r\n").encode())
    return messages


@dataclass
class SsdpServer:
    """Answers searches and announces the server every few minutes."""

    udn: str
    location_for: Callable[[str], str]  # peer address → description URL
    _socket: socket.socket | None = None
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    error: str | None = None

    def start(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with contextlib.suppress(AttributeError, OSError):  # share 1900 with others
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind(("", SSDP_PORT))
            membership = struct.pack("4sl", socket.inet_aton(SSDP_GROUP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(1.0)
        except OSError as exc:
            self.error = f"SSDP (UDP {SSDP_PORT}) nicht verfügbar: {exc}"
            log.warning("DLNA: %s", self.error)
            return False
        self._socket = sock
        self._stop.clear()
        self.error = None
        self._thread = threading.Thread(target=self._run, name="ssdp", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        sock = self._socket
        if sock is not None:
            self._notify(alive=False)
        if self._thread is not None:
            self._thread.join(3)
        if sock is not None:
            sock.close()
        self._socket = None
        self._thread = None

    def _notify(self, alive: bool) -> None:
        sock = self._socket
        if sock is None:
            return
        location = self.location_for(SSDP_GROUP)
        for message in notify_messages(self.udn, location, alive):
            with contextlib.suppress(OSError):
                sock.sendto(message, (SSDP_GROUP, SSDP_PORT))

    def _run(self) -> None:
        sock = self._socket
        assert sock is not None
        next_notify = 0.0
        while not self._stop.is_set():
            if time.monotonic() >= next_notify:
                self._notify(alive=True)
                next_notify = time.monotonic() + MAX_AGE / 4
            try:
                data, (host, port) = sock.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                continue
            if not is_home_network(host):
                continue
            answers = search_responses(data, self.udn, self.location_for(host))
            if answers:
                time.sleep(random.uniform(0, 0.3))  # noqa: S311 – spreading, not security
            for answer in answers:
                with contextlib.suppress(OSError):
                    sock.sendto(answer, (host, port))


# --- service -----------------------------------------------------------------------------

# Name of the settings row holding this server's UPnP identity.
UDN_KEY = "dlna_uuid"


def device_udn(db: Session) -> str:
    """The server's identity – stays the same, so TVs keep their place in the list."""
    row = db.get(Setting, UDN_KEY)
    if row is None or not isinstance(row.value, str):
        value = f"uuid:{uuid.uuid4()}"
        if row is None:
            db.add(Setting(key=UDN_KEY, value=value))
        else:
            row.value = value
        db.commit()
        return value
    return row.value


class DlnaService:
    """Starts and stops the SSDP announcements along with the setting."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        port: int,
        ssdp_factory: Callable[[str, Callable[[str], str]], SsdpServer] = SsdpServer,
    ) -> None:
        self._sessions = sessions
        self._port = port
        self._factory = ssdp_factory
        self._lock = threading.Lock()
        self._server: SsdpServer | None = None
        self.error: str | None = None

    def location_for(self, peer: str) -> str:
        return f"http://{local_ip_for(peer)}:{self._port}/dlna/description.xml"

    @property
    def running(self) -> bool:
        return self._server is not None

    def apply(self) -> None:
        with self._sessions() as db:
            enabled = load_app_settings(db).dlna.enabled
            udn = device_udn(db) if enabled else ""
        with self._lock:
            if enabled and self._server is None:
                server = self._factory(udn, self.location_for)
                if server.start():
                    self._server = server
                    self.error = None
                else:
                    self.error = server.error
            elif not enabled:
                self._stop_locked()
                self.error = None

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        if self._server is not None:
            self._server.stop()
            self._server = None
