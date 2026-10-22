// Source-only bridge contract. Must be wired to the owning Imlight actor.
using System;
using System.Collections.Generic;
using System.Text.Json;

namespace W101Randomizer.Integration;

/// <summary>An unacknowledged instruction fetched from the authenticated loopback bridge.</summary>
public sealed record PendingEffect(long EventId, string RequestId, string Kind, uint TemplateId,
    string? CheckId, string? ClaimKey);

/// <summary>Strictly parses only the three supported persistent game effects.</summary>
public static class PendingEffects {
    public static IReadOnlyList<PendingEffect> Parse(JsonElement document) {
        if (!document.TryGetProperty("events", out var events) || events.ValueKind != JsonValueKind.Array)
            throw new FormatException("expected an events array");
        var results = new List<PendingEffect>();
        long lastId = 0;
        foreach (var entry in events.EnumerateArray()) {
            if (entry.ValueKind != JsonValueKind.Object)
                throw new FormatException("invalid outbox event");
            var eventId = entry.GetProperty("id").GetInt64();
            if (eventId <= lastId)
                throw new FormatException("outbox events must have increasing positive IDs");
            lastId = eventId;
            var request = entry.GetProperty("request_id").GetString();
            if (string.IsNullOrWhiteSpace(request))
                throw new FormatException("event has no request ID");
            var kind = entry.GetProperty("kind").GetString();
            var payload = entry.GetProperty("payload");
            if (payload.ValueKind != JsonValueKind.Object)
                throw new FormatException("invalid event payload");
            string rawId;
            string? checkId = null;
            string? claimKey = null;
            switch (kind) {
                case "spell.grant":
                case "spell.revoke":
                    rawId = payload.GetProperty("spell_id").GetString() ?? "";
                    break;
                case "item.grant":
                    rawId = payload.GetProperty("reward_id").GetString() ?? "";
                    checkId = payload.GetProperty("check_id").GetString();
                    claimKey = payload.GetProperty("claim_key").GetString();
                    if (string.IsNullOrWhiteSpace(checkId) || string.IsNullOrWhiteSpace(claimKey))
                        throw new FormatException("item grant requires check and claim keys");
                    break;
                default:
                    throw new FormatException($"unknown randomizer effect: {kind}");
            }
            if (!uint.TryParse(rawId, out var templateId) || templateId == 0)
                throw new FormatException($"invalid numeric template ID: {rawId}");
            results.Add(new PendingEffect(eventId, request!, kind!, templateId, checkId, claimKey));
        }
        return results;
    }
}

/// <summary>
/// Implement on top of Imlight's authoritative actor-owned character, and call only
/// from its mailbox handler. Every method must persist successfully or throw.
/// Item grants must atomically save an event receipt with the item; never add
/// the item twice on outbox retry.
/// </summary>
public interface IActorOwnedWizardEffects {
    bool HasLearnedSpell(uint spellId);
    void LearnAndSyncSpell(uint spellId);
    void UnlearnAndSyncSpell(uint spellId);
    void GrantItemOnceAndSync(long eventId, uint itemId, string checkId, string claimKey);
}

public static class ActorOwnedEffectApplier {
    /// <summary>
    /// Apply one instruction on the Imlight actor thread. Return the event ID for
    /// an acknowledgment only AFTER the underlying character save and client sync
    /// have succeeded. An HTTP callback must never call this directly.
    /// </summary>
    public static long Apply(PendingEffect item, IActorOwnedWizardEffects wizard) {
        ArgumentNullException.ThrowIfNull(wizard);
        switch (item.Kind) {
            case "spell.grant":
                if (!wizard.HasLearnedSpell(item.TemplateId))
                    wizard.LearnAndSyncSpell(item.TemplateId);
                break;
            case "spell.revoke":
                if (wizard.HasLearnedSpell(item.TemplateId))
                    wizard.UnlearnAndSyncSpell(item.TemplateId);
                break;
            case "item.grant":
                wizard.GrantItemOnceAndSync(item.EventId, item.TemplateId,
                    item.CheckId!, item.ClaimKey!);
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(item), "unknown effect kind");
        }
        return item.EventId;
    }
}
