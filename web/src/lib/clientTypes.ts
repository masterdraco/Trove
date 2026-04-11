import type { ClientType } from "$lib/api";

export type CredentialField = {
  key: string;
  label: string;
  type: "text" | "password";
  required?: boolean;
  placeholder?: string;
};

export type ClientTypeMeta = {
  label: string;
  protocol: "torrent" | "usenet";
  urlPlaceholder: string;
  urlHint: string;
  fields: CredentialField[];
};

export const CLIENT_TYPES: Record<ClientType, ClientTypeMeta> = {
  transmission: {
    label: "Transmission",
    protocol: "torrent",
    urlPlaceholder: "http://192.168.0.10:9091",
    urlHint: "Base URL of the web interface — the driver appends /transmission/rpc.",
    fields: [
      { key: "username", label: "Username", type: "text" },
      { key: "password", label: "Password", type: "password" }
    ]
  },
  deluge: {
    label: "Deluge",
    protocol: "torrent",
    urlPlaceholder: "http://192.168.0.10:8112",
    urlHint: "Base URL of deluge-web (not the daemon RPC port).",
    fields: [
      { key: "password", label: "Web UI password", type: "password", required: true }
    ]
  },
  sabnzbd: {
    label: "SABnzbd",
    protocol: "usenet",
    urlPlaceholder: "http://192.168.0.10:8080",
    urlHint: "Base URL of SABnzbd.",
    fields: [
      { key: "api_key", label: "API key", type: "password", required: true }
    ]
  },
  nzbget: {
    label: "NZBGet",
    protocol: "usenet",
    urlPlaceholder: "http://192.168.0.10:6789",
    urlHint: "Base URL of NZBGet.",
    fields: [
      { key: "username", label: "Username", type: "text", required: true },
      { key: "password", label: "Password", type: "password", required: true }
    ]
  }
};
