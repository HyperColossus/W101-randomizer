// Copyright contributors; available for inclusion in a compatible Imlight fork.
// Integration helper ONLY: this does not hook into the game automatically.
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace W101Randomizer.Integration;

/// <summary>
/// Communicates with a local, authenticated randomizer service.
/// All game mutations must happen in Imlight's owning actor and be made idempotent.
/// The Python service only returns instructions; it NEVER edits character data.
/// </summary>
public sealed class RandomizerClient : IDisposable {
    private readonly HttpClient _client;

    public RandomizerClient(string token, Uri? endpoint = null) {
        endpoint ??= new Uri("http://127.0.0.1:18951/");
        if (!endpoint.IsLoopback || endpoint.Scheme != Uri.UriSchemeHttp)
            throw new ArgumentException("The randomizer service only supports loopback HTTP", nameof(endpoint));
        if (string.IsNullOrWhiteSpace(token) || token.Length < 24)
            throw new ArgumentException("Randomizer token must be 24+ characters", nameof(token));
        _client = new HttpClient { BaseAddress = endpoint, Timeout = TimeSpan.FromSeconds(8) };
        _client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
    }

    private async Task<JsonElement> GetAsync(string path, CancellationToken cancellationToken = default) {
        using var response = await _client.GetAsync(path, cancellationToken);
        response.EnsureSuccessStatusCode();
        using var doc = JsonDocument.Parse(await response.Content.ReadAsStreamAsync(cancellationToken));
        return doc.RootElement.Clone();
    }

    private async Task<JsonElement> PostAsync(string path, object body, CancellationToken cancellationToken = default) {
        using var request = new HttpRequestMessage(HttpMethod.Post, path) {
            Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json")
        };
        using var response = await _client.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        using var doc = JsonDocument.Parse(await response.Content.ReadAsStreamAsync(cancellationToken));
        return doc.RootElement.Clone();
    }

    /// <summary>Send a stable unique request ID for an XP event; retries are safe.</summary>
    public Task<JsonElement> LevelAsync(string characterId, int level, string requestId,
        CancellationToken cancellationToken = default)
        => CommandAsync(characterId, "level", requestId, new { level }, cancellationToken);

    public Task<JsonElement> StartAsync(string characterId, string requestId,
        CancellationToken cancellationToken = default)
        => CommandAsync(characterId, "start", requestId, new { }, cancellationToken);

    public Task<JsonElement> ChooseDraftAsync(string characterId, int level, string spellId, string requestId,
        CancellationToken cancellationToken = default)
        => CommandAsync(characterId, "draft", requestId, new { level, spell_id = spellId }, cancellationToken);

    public Task<JsonElement> RerollAsync(string characterId, string spellId, string requestId,
        CancellationToken cancellationToken = default)
        => CommandAsync(characterId, "reroll", requestId, new { spell_id = spellId }, cancellationToken);

    public Task<JsonElement> GrantTokensAsync(string characterId, int count, string requestId,
        CancellationToken cancellationToken = default)
        => CommandAsync(characterId, "tokens", requestId, new { count }, cancellationToken);

    public Task<JsonElement> ClaimRewardAsync(string characterId, string checkId,
        string requestId, string? encounterId = null, CancellationToken cancellationToken = default)
        => CommandAsync(characterId, "claim", requestId,
            new { check_id = checkId, encounter_id = encounterId }, cancellationToken);

    public Task<JsonElement> CommandAsync(string characterId, string action, string requestId,
        object payload, CancellationToken cancellationToken = default)
        => PostAsync("v1/commands", new {
            actor = characterId, action, request_id = requestId, payload
        }, cancellationToken);

    /// <summary>Find unapplied effects after startup, crash, or interrupted command.</summary>
    public Task<JsonElement> PendingAsync(string characterId, CancellationToken cancellationToken = default)
        => GetAsync("v1/characters/" + Uri.EscapeDataString(characterId) + "/pending", cancellationToken);

    public Task<JsonElement> CharacterAsync(string characterId, CancellationToken cancellationToken = default)
        => GetAsync("v1/characters/" + Uri.EscapeDataString(characterId), cancellationToken);

    /// <summary>Look up deterministic encounter/NPC/boss/loot/portal mapping by catalog slot ID.</summary>
    public Task<JsonElement> ResolveAsync(string category, string slotId, CancellationToken cancellationToken = default)
        => GetAsync("v1/world/" + Uri.EscapeDataString(category) + "/" + Uri.EscapeDataString(slotId), cancellationToken);

    /// <summary>ONLY call after Imlight's authoritative save and client sync succeed.</summary>
    public Task<JsonElement> AckAsync(string characterId, long eventId, CancellationToken cancellationToken = default)
        => PostAsync("v1/ack", new { actor = characterId, event_id = eventId }, cancellationToken);

    public void Dispose() => _client.Dispose();
}
