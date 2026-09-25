"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import type { BBox, Label, Lead } from "@/lib/types";

const TILE_URL =
  "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

function scoreColor(lead: Lead): string {
  if (lead.reasons.length === 0) return "#5b6270"; // not yet scored
  if (lead.score >= 65) return "var(--lime)";
  if (lead.score >= 35) return "var(--amber)";
  return "var(--coral)";
}

function pinIcon(lead: Lead, label: Label | undefined, selected: boolean): L.DivIcon {
  const dot = scoreColor(lead);
  const ringColor = label === "good" ? "#d4ff3a" : label === "bad" ? "#ff5a4e" : "transparent";
  const size = selected ? 16 : 12;
  const ring = label
    ? `box-shadow: 0 0 0 2px ${ringColor}, 0 0 0 3.5px #0a0b0d;`
    : `box-shadow: 0 0 0 1.5px #0a0b0d;`;
  return L.divIcon({
    className: "prospector-pin-wrapper motion-ok",
    html: `<div class="pin-drop prospector-pin" style="width:${size}px;height:${size}px;background:${dot};${ring}"></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function radarIcon(): L.DivIcon {
  return L.divIcon({
    className: "motion-ok",
    html:
      '<div style="width:280px;height:280px;border-radius:9999px;overflow:hidden;' +
      'background:radial-gradient(circle, rgba(212,255,58,0.05) 0%, transparent 70%);' +
      'border:1px solid rgba(212,255,58,0.25);position:relative;">' +
      '<div class="radar-sweep" style="position:absolute;inset:0;border-radius:9999px;' +
      'background:conic-gradient(from 0deg, rgba(212,255,58,0.35), transparent 35%);' +
      'transform-origin:center;"></div></div>',
    iconSize: [280, 280],
    iconAnchor: [140, 140],
  });
}

function bboxCenter(bbox: BBox): [number, number] {
  return [(bbox.south + bbox.north) / 2, (bbox.west + bbox.east) / 2];
}

function FitToData({ bbox, leads }: { bbox: BBox | null; leads: Lead[] }) {
  const map = useMap();
  const fittedKeyRef = useRef<string>("");

  useEffect(() => {
    const key = bbox
      ? `bbox:${bbox.south},${bbox.west},${bbox.north},${bbox.east}`
      : `leads:${leads.length}`;
    if (key === fittedKeyRef.current) return;
    fittedKeyRef.current = key;

    if (bbox) {
      map.fitBounds(
        [
          [bbox.south, bbox.west],
          [bbox.north, bbox.east],
        ],
        { padding: [24, 24] }
      );
    } else if (leads.length > 0) {
      const bounds = L.latLngBounds(leads.map((l) => [l.lat, l.lon]));
      map.fitBounds(bounds, { padding: [32, 32] });
    }
  }, [bbox, leads, map]);

  return null;
}

interface ProspectorMapProps {
  leads: Lead[];
  labels?: Record<string, Label>;
  bbox: BBox | null;
  selectedId?: string | null;
  onSelect?: (leadId: string) => void;
  /** True while the agent is mid geocode/search_businesses/widen_area, to
   * show a radar sweep centred on the bbox. */
  sweeping?: boolean;
}

export default function ProspectorMap({
  leads,
  labels,
  bbox,
  selectedId,
  onSelect,
  sweeping = false,
}: ProspectorMapProps) {
  const center = useMemo<[number, number]>(
    () => (bbox ? bboxCenter(bbox) : leads[0] ? [leads[0].lat, leads[0].lon] : [20.5937, 78.9629]),
    [bbox, leads]
  );

  return (
    // react-leaflet's MapContainerProps doesn't forward arbitrary data-*
    // attributes to the DOM, so the test hook lives on this wrapper div.
    <div className="h-full w-full" data-testid="prospector-map">
      <MapContainer center={center} zoom={bbox ? 12 : 4} scrollWheelZoom className="h-full w-full">
        <TileLayer url={TILE_URL} attribution={ATTRIBUTION} />
        <FitToData bbox={bbox} leads={leads} />

        {sweeping && bbox && (
          <Marker position={bboxCenter(bbox)} icon={radarIcon()} interactive={false} zIndexOffset={-1000} />
        )}

        {leads.map((lead) => (
          <Marker
            key={lead.id}
            position={[lead.lat, lead.lon]}
            icon={pinIcon(lead, labels?.[lead.id], selectedId === lead.id)}
            eventHandlers={{
              click: () => onSelect?.(lead.id),
            }}
          />
        ))}
      </MapContainer>
    </div>
  );
}
