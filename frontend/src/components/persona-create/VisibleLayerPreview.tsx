"use client";

import type { ReactNode } from "react";

import {
  EMOJI_USAGE_LABELS,
  INITIATIVE_PATTERN_LABELS,
  MESSAGE_LENGTH_LABELS,
} from "@/lib/persona-visible-enums";
import { VISIBLE_LABELS } from "@/lib/persona-visible-labels";
import {
  enumDisplayLabel,
  filterStringList,
  isNonemptyScalar,
  showInitiativePattern,
} from "@/lib/persona-visible-visibility";
import type {
  BasicInfoV06,
  ObservableChatStyleV06,
  RelationshipWithUserV06,
  VisibleLayerV06,
} from "@/types/persona";

function LabelRow({ pathKey, children }: { pathKey: string; children: ReactNode }) {
  const title = VISIBLE_LABELS[pathKey] ?? pathKey;
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="text-muted-foreground mb-1 text-xs">{title}</div>
      <div className="whitespace-pre-wrap text-sm">{children}</div>
    </div>
  );
}

function Section({
  sectionTitlePathKey,
  children,
}: {
  sectionTitlePathKey: string;
  children: ReactNode;
}) {
  const title = VISIBLE_LABELS[sectionTitlePathKey];
  return (
    <div className="space-y-2 rounded-lg border bg-muted/20 p-3">
      {title ? <div className="text-sm font-medium">{title}</div> : null}
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function BasicInfoBlock({ bi }: { bi: BasicInfoV06 }) {
  const rows = (
    [
      { pathKey: "basic_info.gender", val: bi.gender },
      { pathKey: "basic_info.age_or_life_stage", val: bi.age_or_life_stage },
      { pathKey: "basic_info.identity_role", val: bi.identity_role },
      { pathKey: "basic_info.location_context", val: bi.location_context },
      { pathKey: "basic_info.relationship_status", val: bi.relationship_status },
    ] as const
  ).filter((r) => isNonemptyScalar(r.val));

  if (!rows.length) return null;
  return (
    <Section sectionTitlePathKey="basic_info._section">
      {rows.map((r) => (
        <LabelRow key={r.pathKey} pathKey={r.pathKey}>
          {String(r.val)}
        </LabelRow>
      ))}
    </Section>
  );
}

function RelationshipBlock({ ru }: { ru: RelationshipWithUserV06 }) {
  const rows = (
    [
      { pathKey: "relationship_with_user.known_context", val: ru.known_context },
      {
        pathKey: "relationship_with_user.interaction_frequency",
        val: ru.interaction_frequency,
      },
      {
        pathKey: "relationship_with_user.current_interaction_summary",
        val: ru.current_interaction_summary,
      },
    ] as const
  ).filter((r) => isNonemptyScalar(r.val));

  if (!rows.length) return null;
  return (
    <Section sectionTitlePathKey="relationship_with_user._section">
      {rows.map((r) => (
        <LabelRow key={r.pathKey} pathKey={r.pathKey}>
          {String(r.val)}
        </LabelRow>
      ))}
    </Section>
  );
}

function ObservableChatStyleBlock({ obs }: { obs: ObservableChatStyleV06 }) {
  const ml = enumDisplayLabel(obs.message_length, MESSAGE_LENGTH_LABELS);
  const em = enumDisplayLabel(obs.emoji_usage, EMOJI_USAGE_LABELS);
  const iniRaw = obs.initiative_pattern;
  const iniZh =
    iniRaw && showInitiativePattern(iniRaw)
      ? INITIATIVE_PATTERN_LABELS[iniRaw.trim()] ?? iniRaw.trim()
      : null;
  const expr = filterStringList(obs.expression_features);
  const phrases = filterStringList(obs.typical_phrases);

  const parts: ReactNode[] = [];
  if (ml) {
    parts.push(
      <LabelRow key="ml" pathKey="observable_chat_style.message_length">
        {ml}
      </LabelRow>,
    );
  }
  if (em) {
    parts.push(
      <LabelRow key="em" pathKey="observable_chat_style.emoji_usage">
        {em}
      </LabelRow>,
    );
  }
  if (iniZh) {
    parts.push(
      <LabelRow key="ini" pathKey="observable_chat_style.initiative_pattern">
        {iniZh}
      </LabelRow>,
    );
  }
  if (expr.length) {
    parts.push(
      <LabelRow key="ex" pathKey="observable_chat_style.expression_features">
        <ul className="list-inside list-disc">
          {expr.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      </LabelRow>,
    );
  }
  if (phrases.length) {
    parts.push(
      <LabelRow key="ph" pathKey="observable_chat_style.typical_phrases">
        <ul className="list-inside list-disc">
          {phrases.map((x, i) => (
            <li key={i}>{x}</li>
          ))}
        </ul>
      </LabelRow>,
    );
  }

  if (!parts.length) return null;
  return <Section sectionTitlePathKey="observable_chat_style._section">{parts}</Section>;
}

export function VisibleLayerPreview({ vl }: { vl: VisibleLayerV06 }) {
  const prefs = vl.explicit_preferences;
  const likes = filterStringList(prefs.likes);
  const dislikes = filterStringList(prefs.dislikes);

  const personality = filterStringList(vl.explicit_personality_notes);
  const interests = filterStringList(vl.explicit_interests);

  return (
    <div className="space-y-3">
      {isNonemptyScalar(vl.display_name) ? (
        <LabelRow pathKey="display_name">{vl.display_name!.trim()}</LabelRow>
      ) : null}

      <BasicInfoBlock bi={vl.basic_info} />
      <RelationshipBlock ru={vl.relationship_with_user} />

      {personality.length ? (
        <Section sectionTitlePathKey="explicit_personality_notes">
          <ul className="list-inside list-disc space-y-1">
            {personality.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </Section>
      ) : null}

      {interests.length ? (
        <Section sectionTitlePathKey="explicit_interests">
          <ul className="list-inside list-disc space-y-1">
            {interests.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </Section>
      ) : null}

      {likes.length || dislikes.length ? (
        <Section sectionTitlePathKey="explicit_preferences._section">
          {likes.length ? (
            <LabelRow pathKey="explicit_preferences.likes">
              <ul className="list-inside list-disc">
                {likes.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </LabelRow>
          ) : null}
          {dislikes.length ? (
            <LabelRow pathKey="explicit_preferences.dislikes">
              <ul className="list-inside list-disc">
                {dislikes.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </LabelRow>
          ) : null}
        </Section>
      ) : null}

      <ObservableChatStyleBlock obs={vl.observable_chat_style} />

      {isNonemptyScalar(vl.visible_background) ? (
        <LabelRow pathKey="visible_background">{vl.visible_background!.trim()}</LabelRow>
      ) : null}
    </div>
  );
}
