using System;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Windows.Media.Control;
using Windows.Storage.Streams;

namespace MediaBridge;

/// <summary>
/// Bridges the Windows media session (what the volume flyout shows) to
/// unidesk over stdio. Writes one JSON object per line on every change:
///   {"type":"media","playing":null}
///   {"type":"media","playing":{app,title,artist,album,status,position,duration,updatedAt,art?}}
/// "art" (a data: URL) is only sent when the cover changes; otherwise it is
/// absent and the last one still applies. Reads commands, one per line:
///   play-pause | next | previous | seek &lt;seconds&gt;
/// </summary>
public static class Program
{
    private static readonly object WriteLock = new();
    private static readonly SemaphoreSlim Gate = new(1, 1);
    private static GlobalSystemMediaTransportControlsSessionManager _manager = null!;
    private static GlobalSystemMediaTransportControlsSession? _session;
    private static string? _artKey;
    private static string _artHash = "";

    private static async Task RecheckArtSoon(string key)
    {
        foreach (var delay in new[] { 700, 2000, 4500 })
        {
            await Task.Delay(delay);
            if (key != _artKey) return;
            await Update();
        }
    }

    public static async Task Main()
    {
        Console.OutputEncoding = new System.Text.UTF8Encoding(false);
        Console.InputEncoding = new System.Text.UTF8Encoding(false);
        _manager = await GlobalSystemMediaTransportControlsSessionManager.RequestAsync();
        _manager.CurrentSessionChanged += (_, _) => _ = Update();
        _manager.SessionsChanged += (_, _) => _ = Update();
        await Update();

        string? line;
        while ((line = await Console.In.ReadLineAsync()) != null)
        {
            try { await Command(line.Trim()); }
            catch (Exception e) { Write(new { type = "error", message = $"{line.Trim()}: {e.GetType().Name} 0x{e.HResult:X8} {e.Message}" }); }
        }
    }

    private static async Task Command(string line)
    {
        // WinRT session objects are tied to the thread that fetched them (commands
        // from another thread fail with RPC_E_WRONG_THREAD), so look it up again here.
        var aumid = _session?.SourceAppUserModelId;
        if (aumid == null) return;
        var manager = await GlobalSystemMediaTransportControlsSessionManager.RequestAsync();
        GlobalSystemMediaTransportControlsSession? s = null;
        foreach (var candidate in manager.GetSessions())
        {
            if (candidate.SourceAppUserModelId == aumid) { s = candidate; break; }
        }
        if (s == null) return;
        if (line == "play-pause")
        {
            // Some players don't implement the toggle; use play / pause directly.
            var status = s.GetPlaybackInfo()?.PlaybackStatus;
            var ok = status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing
                ? await s.TryPauseAsync()
                : await s.TryPlayAsync();
            if (!ok) await s.TryTogglePlayPauseAsync();
        }
        else if (line == "next") await s.TrySkipNextAsync();
        else if (line == "previous") await s.TrySkipPreviousAsync();
        else if (line.StartsWith("seek ") && double.TryParse(line[5..], System.Globalization.NumberStyles.Float,
                     System.Globalization.CultureInfo.InvariantCulture, out var seconds))
        {
            var start = s.GetTimelineProperties()?.StartTime ?? TimeSpan.Zero;
            await s.TryChangePlaybackPositionAsync((start + TimeSpan.FromSeconds(seconds)).Ticks);
        }
    }

    private static void OnSessionEvent(GlobalSystemMediaTransportControlsSession sender, object args) => _ = Update();

    /// <summary>Pick the session that is playing (else Windows' current one) and report it.</summary>
    private static async Task Update()
    {
        await Gate.WaitAsync();
        try
        {
            GlobalSystemMediaTransportControlsSession? pick = null;
            foreach (var s in _manager.GetSessions())
            {
                if (s.GetPlaybackInfo()?.PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing)
                {
                    pick = s;
                    break;
                }
            }
            pick ??= _manager.GetCurrentSession();

            if (pick?.SourceAppUserModelId != _session?.SourceAppUserModelId)
            {
                if (_session != null)
                {
                    _session.MediaPropertiesChanged -= OnSessionEvent;
                    _session.PlaybackInfoChanged -= OnSessionEvent;
                    _session.TimelinePropertiesChanged -= OnSessionEvent;
                }
                _session = pick;
                _artKey = null;
                _artHash = "";
                if (_session != null)
                {
                    _session.MediaPropertiesChanged += OnSessionEvent;
                    _session.PlaybackInfoChanged += OnSessionEvent;
                    _session.TimelinePropertiesChanged += OnSessionEvent;
                }
            }

            var session = _session;
            if (session == null)
            {
                Write(new { type = "media", playing = (object?)null });
                return;
            }

            GlobalSystemMediaTransportControlsSessionMediaProperties? props = null;
            try { props = await session.TryGetMediaPropertiesAsync(); } catch { }
            var info = session.GetPlaybackInfo();
            if (props == null || string.IsNullOrWhiteSpace(props.Title)
                || info?.PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Closed)
            {
                _artKey = null;
                _artHash = "";
                Write(new { type = "media", playing = (object?)null });
                return;
            }

            var t = session.GetTimelineProperties();
            var duration = t == null ? 0 : (t.EndTime - t.StartTime).TotalSeconds;
            var position = t == null ? 0 : (t.Position - t.StartTime).TotalSeconds;
            var updatedAt = t == null ? DateTimeOffset.Now : t.LastUpdatedTime;

            // Players often publish the new title before the new cover, so the
            // first thumbnail after a track change can still be the old one.
            // Re-read the cover on every update, send it only when its bytes
            // change, and look again shortly after a track change.
            string? art = null;
            var key = session.SourceAppUserModelId + "|" + props.Title + "|" + props.Artist;
            var read = await ReadArt(props.Thumbnail);
            var hash = read == null ? "" : read.Length + ":" + read.GetHashCode();
            if (key != _artKey)
            {
                _artKey = key;
                _ = RecheckArtSoon(key);
            }
            if (hash != _artHash)
            {
                _artHash = hash;
                art = read ?? "";
            }

            Write(new
            {
                type = "media",
                playing = new
                {
                    app = session.SourceAppUserModelId,
                    title = props.Title,
                    artist = props.Artist,
                    album = props.AlbumTitle,
                    status = info?.PlaybackStatus switch
                    {
                        GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing => "playing",
                        GlobalSystemMediaTransportControlsSessionPlaybackStatus.Paused => "paused",
                        _ => "stopped",
                    },
                    position,
                    duration,
                    updatedAt = updatedAt.ToUnixTimeMilliseconds(),
                    art,
                },
            });
        }
        catch (Exception e)
        {
            Write(new { type = "error", message = e.Message });
        }
        finally
        {
            Gate.Release();
        }
    }

    private static async Task<string?> ReadArt(IRandomAccessStreamReference? reference)
    {
        if (reference == null) return null;
        try
        {
            using var stream = await reference.OpenReadAsync();
            if (stream.Size == 0) return null;
            using var input = stream.AsStreamForRead();
            using var memory = new MemoryStream();
            await input.CopyToAsync(memory);
            var bytes = memory.ToArray();
            var mime = bytes.Length > 3 && bytes[0] == 0x89 && bytes[1] == 0x50 ? "image/png" : "image/jpeg";
            return $"data:{mime};base64,{Convert.ToBase64String(bytes)}";
        }
        catch
        {
            return null;
        }
    }

    private static void Write(object value)
    {
        var json = JsonSerializer.Serialize(value, new JsonSerializerOptions { DefaultIgnoreCondition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull });
        lock (WriteLock)
        {
            Console.Out.WriteLine(json);
            Console.Out.Flush();
        }
    }
}
