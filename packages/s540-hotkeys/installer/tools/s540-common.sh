#!/bin/bash
# macOS 13+ Intel. Install only the two verified bundles and this user's LaunchAgent.
# No EFI, boot arguments, SIP, NVRAM or third-party driver is modified.
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export LC_ALL=C
umask 077

S540_KEXT_ID=org.s540.HotkeysVPC
S540_APP_ID=org.s540.Hotkeys
S540_KEXT_VERSION=0.1.0
S540_APP_VERSION=0.1.2
S540_V1_APP_MANIFEST_SHA256=05bfcf271293f1e11e9def08acfddb4f7330adeda1f35243fea1ae6567cf3bb1
S540_V11_APP_MANIFEST_SHA256=c44f5b94bbd7daa127072973460136d79318c8ae7e40e2a22572cfc4e8c57c20
S540_V1_KEXT_MANIFEST_SHA256=13f6070000c5487f67ce5e9acf30face88d189e89d1bf005d7f36009395b946c
S540_LABEL=org.s540.Hotkeys
S540_KEXT=/Library/Extensions/S540HotkeysVPC.kext
S540_APP=/Applications/S540Tasti.app
S540_APP_BIN="$S540_APP/Contents/MacOS/S540Tasti"
S540_ROOT='/Library/Application Support/S540Tasti'
S540_RECEIPT="$S540_ROOT/receipt.plist"
S540_LOCK='/Library/Application Support/S540Tasti.install-lock'
S540_UID=$(/usr/bin/id -u)
S540_AGENT="$HOME/Library/LaunchAgents/$S540_LABEL.plist"
S540_RUN=''
S540_RUN_ID=''
S540_STAGE=''
S540_LOCKED=0
S540_CREATED_KEXT=0
S540_CREATED_APP=0
S540_CREATED_AGENT=0
S540_BOOTSTRAPPED=0
S540_LOADED_HERE=0
S540_RECEIPT_OURS=0
S540_PRESERVE=0
S540_INSTALL_DONE=0
S540_INSTALL_MUTATION_STARTED=0
S540_CACHE_REMOVAL_PENDING=0
S540_UNLOAD_PENDING=0
S540_DRIVER_STATE=''
S540_UPGRADE_ACTIVE=0
S540_UPGRADE_OLD_APP_MOVED=0
S540_UPGRADE_NEW_APP_INSTALLED=0
S540_UPGRADE_BACKUP=''
S540_UPGRADE_RECEIPT_SHA256=''
S540_UPGRADE_AGENT_SHA256=''
S540_UPGRADE_SOURCE_APP_SHA256=''
S540_UPGRADE_PRIOR_PATH=''
S540_UPGRADE_PRIOR_SHA256=''
S540_OPERATION=verify

s540_fail() { printf '\nSTOP: %s\n' "$1" >&2; return 1; }
s540_hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
s540_plist() { /usr/bin/plutil -extract "$2" raw -expect "$3" -o - "$1"; }

s540_host() {
    [ "$(/usr/bin/uname -s)" = Darwin ] && [ "$(/usr/bin/uname -m)" = x86_64 ] || s540_fail 'Servono macOS e un processore Intel.'
    [ "$(/usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null || printf 0)" != 1 ] || s540_fail 'Questo pacchetto richiede un Mac Intel; Rosetta non è sufficiente.'
    local major
    major=$(/usr/bin/sw_vers -productVersion); major=${major%%.*}
    [ "$major" -ge 13 ] || s540_fail 'Serve macOS 13 o successivo.'
    [ "$S540_UID" != 0 ] && [ "$S540_UID" = "$(/usr/bin/id -ru)" ] || s540_fail 'Esegui dal tuo utente, senza sudo davanti al comando.'
    [ -d "$HOME" ] && [ "$(/usr/bin/stat -f %u "$HOME")" = "$S540_UID" ] || s540_fail 'La cartella utente non corrisponde all’utente corrente.'
    /bin/launchctl print "gui/$S540_UID" >/dev/null 2>&1 || s540_fail 'Avvia dal Terminale della tua sessione grafica macOS.'
}

s540_new_run() {
    local parent
    S540_RUN_ID=$(/usr/bin/uuidgen)
    parent="$HOME/Library/Application Support/S540Tasti/Installazioni"
    /bin/mkdir -p "$parent"
    S540_RUN=$(/usr/bin/mktemp -d "$parent/$S540_RUN_ID.XXXXXX")
    /bin/chmod 700 "$S540_RUN"
    printf 'Operazione: %s\nUID: %s\n' "$S540_OPERATION" "$S540_UID" > "$S540_RUN/status.txt"
    printf 'Log: %s\n' "$S540_RUN"
}

# Includes empty directories, excludes symlinks, and detects extra/missing files.
s540_tree_manifest() {
    local directory="$1" output="$2" links
    [ -d "$directory" ] && [ ! -L "$directory" ] || return 1
    links=$(/usr/bin/find "$directory" -type l -print) || return 1
    [ -z "$links" ] || return 1
    (
        cd "$directory"
        { /usr/bin/find . -type d -print | /usr/bin/sed 's/^/D /'
          /usr/bin/find . -type f -exec /usr/bin/shasum -a 256 {} + | /usr/bin/sed 's/^/F /'
        } | /usr/bin/sort
    ) > "$output"
}

s540_tree_matches() {
    s540_tree_manifest "$1" "$S540_RUN/tree-current.txt" || return 1
    /usr/bin/cmp -s "$2" "$S540_RUN/tree-current.txt"
}

s540_package() {
    [ -f "$S540_PACKAGE/SHA256SUMS" ] && [ ! -L "$S540_PACKAGE/SHA256SUMS" ] || s540_fail 'SHA256SUMS manca: estrai il pacchetto completo.'
    /usr/bin/awk 'length($1)!=64 || $1 ~ /[^0-9a-f]/ || substr($0,65,2)!="  " || substr($0,67) ~ /^\// || substr($0,67) ~ /(^|\/)\.\.($|\/)/ {bad=1} END {exit bad}' "$S540_PACKAGE/SHA256SUMS" || s540_fail 'Manifest del pacchetto non valido.'
    (cd "$S540_PACKAGE" && /usr/bin/shasum -a 256 -c SHA256SUMS) > "$S540_RUN/package-check.log" 2>&1 || s540_fail 'Pacchetto incompleto o modificato. Vedi package-check.log.'
    local component path executable
    for component in S540HotkeysVPC.kext S540Tasti.app; do
        path="$S540_PACKAGE/assets/$component"
        [ -d "$path" ] && [ ! -L "$path" ] || s540_fail "Manca assets/$component."
        /usr/bin/codesign --verify --strict "$path" > "$S540_RUN/$component-codesign.log" 2>&1 || s540_fail "Firma non valida per $component."
    done
    [ "$(s540_plist "$S540_PACKAGE/assets/S540HotkeysVPC.kext/Contents/Info.plist" CFBundleIdentifier string)" = "$S540_KEXT_ID" ] || s540_fail 'Identificatore driver inatteso.'
    [ "$(s540_plist "$S540_PACKAGE/assets/S540Tasti.app/Contents/Info.plist" CFBundleIdentifier string)" = "$S540_APP_ID" ] || s540_fail 'Identificatore app inatteso.'
    [ "$(s540_plist "$S540_PACKAGE/assets/S540HotkeysVPC.kext/Contents/Info.plist" CFBundleVersion string)" = "$S540_KEXT_VERSION" ] || s540_fail 'Versione driver inattesa.'
    [ "$(s540_plist "$S540_PACKAGE/assets/S540Tasti.app/Contents/Info.plist" CFBundleVersion string)" = "$S540_APP_VERSION" ] || s540_fail 'Versione app inattesa.'
    s540_tree_manifest "$S540_PACKAGE/assets/S540HotkeysVPC.kext" "$S540_RUN/kext.manifest" || s540_fail 'Struttura driver non valida.'
    s540_tree_manifest "$S540_PACKAGE/assets/S540Tasti.app" "$S540_RUN/app.manifest" || s540_fail 'Struttura app non valida.'
    executable="$S540_PACKAGE/assets/S540Tasti.app/Contents/MacOS/S540Tasti"
    [ -x "$executable" ] || s540_fail 'Il programma S540Tasti non è eseguibile.'
    "$executable" --self-test > "$S540_RUN/app-self-test.json" 2> "$S540_RUN/app-self-test.stderr" || s540_fail 'Controllo iniziale dell’app non superato.'
}

s540_protected() {
    [ -e "$1" ] && [ ! -L "$1" ] && [ "$(/usr/bin/stat -f %u "$1")" = 0 ] || return 1
    [ -z "$(/usr/bin/find "$1" \( -perm -0020 -o -perm -0002 \) -print)" ]
}

s540_receipt_valid() {
    s540_protected "$S540_ROOT" && s540_protected "$S540_RECEIPT" || return 1
    [ "$(s540_plist "$S540_RECEIPT" Schema integer)" = 1 ] &&
    [ "$(s540_plist "$S540_RECEIPT" OwnerUID integer)" = "$S540_UID" ] &&
    [ "$(s540_plist "$S540_RECEIPT" KextPath string)" = "$S540_KEXT" ] &&
    [ "$(s540_plist "$S540_RECEIPT" AppPath string)" = "$S540_APP" ] &&
    [ "$(s540_plist "$S540_RECEIPT" AgentPath string)" = "$S540_AGENT" ] &&
    [ "$(s540_plist "$S540_RECEIPT" BundleID string)" = "$S540_KEXT_ID" ] &&
    [ "$(s540_plist "$S540_RECEIPT" LaunchLabel string)" = "$S540_LABEL" ] || return 1
    [ -f "$S540_ROOT/kext.manifest" ] && [ -f "$S540_ROOT/app.manifest" ] || return 1
    [ "$(s540_hash "$S540_ROOT/kext.manifest")" = "$(s540_plist "$S540_RECEIPT" KextManifestSHA256 string)" ] &&
    [ "$(s540_hash "$S540_ROOT/app.manifest")" = "$(s540_plist "$S540_RECEIPT" AppManifestSHA256 string)" ] || return 1
    S540_RECEIPT_OURS=1
}

s540_owned_paths() {
    if [ -e "$S540_KEXT" ] || [ -L "$S540_KEXT" ]; then
        s540_tree_matches "$S540_KEXT" "$S540_ROOT/kext.manifest" && s540_protected "$S540_KEXT" || return 1
    fi
    if [ -e "$S540_APP" ] || [ -L "$S540_APP" ]; then
        s540_tree_matches "$S540_APP" "$S540_ROOT/app.manifest" && s540_protected "$S540_APP" || return 1
    fi
    if [ -e "$S540_AGENT" ] || [ -L "$S540_AGENT" ]; then
        [ -f "$S540_AGENT" ] && [ ! -L "$S540_AGENT" ] && [ "$(/usr/bin/stat -f %u "$S540_AGENT")" = "$S540_UID" ] &&
        [ "$(s540_hash "$S540_AGENT")" = "$(s540_plist "$S540_RECEIPT" AgentSHA256 string)" ] || return 1
    fi
}

s540_take_lock() {
    /usr/bin/sudo -v || return 1
    /usr/bin/sudo -n /bin/mkdir "$S540_LOCK" 2> "$S540_RUN/lock.stderr" || s540_fail 'Un’altra operazione è in corso oppure esiste un lock da verificare.'
    S540_LOCKED=1
    printf '%s\n' "$S540_RUN_ID" | /usr/bin/sudo -n /usr/bin/tee "$S540_LOCK/owner" >/dev/null
}

s540_release_lock() {
    if [ "$S540_LOCKED" = 1 ] && [ "$(/usr/bin/sudo -n /bin/cat "$S540_LOCK/owner" 2>/dev/null)" = "$S540_RUN_ID" ]; then
        /usr/bin/sudo -n /bin/rm -f "$S540_LOCK/owner" || true
        /usr/bin/sudo -n /bin/rmdir "$S540_LOCK" || true
        S540_LOCKED=0
    fi
}

# Distinguish an absent bundle from a failed query; never treat failed output as absence.
s540_loaded() {
    local id="$1"
    /usr/bin/kmutil showloaded --list-only --bundle-identifier "$id" > "$S540_RUN/loaded.txt" 2> "$S540_RUN/loaded.stderr" || return 2
    /usr/bin/awk -v wanted="$id" '{for(i=1;i<=NF;i++)if($i==wanted)found=1} END{exit !found}' "$S540_RUN/loaded.txt"
}

s540_service_exists() {
    /usr/sbin/ioreg -r -c S540HotkeysVPC -w0 > "$S540_RUN/service.txt" 2> "$S540_RUN/service.stderr" || return 2
    /usr/bin/grep -q '<class S540HotkeysVPC,' "$S540_RUN/service.txt"
}

s540_ready() {
    # Keep the driver's event ring in memory; installation logs contain no key events.
    local snapshot version ready
    S540_DRIVER_STATE=''
    snapshot=$(/usr/sbin/ioreg -a -r -c S540HotkeysVPC -l -w0 2> "$S540_RUN/service.stderr") || return 1
    version=$(printf '%s' "$snapshot" | /usr/bin/plutil -extract 0.Version raw -expect string -o - - 2>/dev/null) || return 1
    ready=$(printf '%s' "$snapshot" | /usr/bin/plutil -extract 0.Ready raw -expect bool -o - - 2>/dev/null) || return 1
    S540_DRIVER_STATE=$(printf '%s' "$snapshot" | /usr/bin/plutil -extract 0.State raw -expect string -o - - 2>/dev/null) || return 1
    [ "$version" = "$S540_KEXT_VERSION" ] && [ "$ready" = true ] && [ "$S540_DRIVER_STATE" = Ready ]
}

s540_competitors() {
    /usr/bin/kmutil showloaded --list-only > "$S540_RUN/loaded-all.txt" 2> "$S540_RUN/loaded-all.stderr" || s540_fail 'Non posso verificare i driver già caricati.'
    if /usr/bin/grep -Ei 'YogaSMC|ReYogaSMC' "$S540_RUN/loaded-all.txt" > "$S540_RUN/competitors.txt"; then
        s540_fail 'YogaSMC/ReYogaSMC è già attivo: nessun driver viene scaricato automaticamente.'; return 1
    fi
    local class
    for class in YogaVPC IdeaVPC YogaSMC ReYogaSMC; do
        /usr/sbin/ioreg -r -c "$class" -l -w0 > "$S540_RUN/competitor-$class.txt" 2> "$S540_RUN/competitor-$class.stderr" || return 1
        if /usr/bin/grep -q '<class ' "$S540_RUN/competitor-$class.txt"; then
            s540_fail "Servizio concorrente $class presente: installazione fermata."; return 1
        fi
    done
}

s540_make_agent() {
    local draft="$S540_RUN/agent.plist"
    /usr/bin/plutil -create xml1 "$draft"
    /usr/bin/plutil -insert Label -string "$S540_LABEL" "$draft"
    /usr/bin/plutil -insert ProgramArguments -array "$draft"
    /usr/bin/plutil -insert ProgramArguments.0 -string "$S540_APP_BIN" "$draft"
    /usr/bin/plutil -insert RunAtLoad -bool true "$draft"
    /usr/bin/plutil -insert KeepAlive -dictionary "$draft"
    /usr/bin/plutil -insert KeepAlive.SuccessfulExit -bool false "$draft"
    /usr/bin/plutil -insert ProcessType -string Interactive "$draft"
    /usr/bin/plutil -insert LimitLoadToSessionType -string Aqua "$draft"
    /usr/bin/plutil -insert ExitTimeOut -integer 30 "$draft"
    /usr/bin/plutil -insert StandardOutPath -string /dev/null "$draft"
    /usr/bin/plutil -insert StandardErrorPath -string /dev/null "$draft"
    /bin/chmod 600 "$draft"
}

s540_write_receipt() {
    local draft="$S540_RUN/receipt.plist" key value
    /usr/bin/plutil -create xml1 "$draft"
    /usr/bin/plutil -insert Schema -integer 1 "$draft"
    /usr/bin/plutil -insert OwnerUID -integer "$S540_UID" "$draft"
    for key in RunID State KextPath AppPath AgentPath BundleID LaunchLabel Version KextVersion AppVersion PackageManifestSHA256 KextManifestSHA256 AppManifestSHA256 AgentSHA256 RunDirectory; do
        case "$key" in
            RunID) value="$S540_RUN_ID";; State) value=prepared;; KextPath) value="$S540_KEXT";;
            AppPath) value="$S540_APP";; AgentPath) value="$S540_AGENT";; BundleID) value="$S540_KEXT_ID";;
            LaunchLabel) value="$S540_LABEL";; Version|AppVersion) value="$S540_APP_VERSION";; KextVersion) value="$S540_KEXT_VERSION";;
            PackageManifestSHA256) value=$(s540_hash "$S540_PACKAGE/SHA256SUMS");;
            KextManifestSHA256) value=$(s540_hash "$S540_RUN/kext.manifest");;
            AppManifestSHA256) value=$(s540_hash "$S540_RUN/app.manifest");;
            AgentSHA256) value=$(s540_hash "$S540_RUN/agent.plist");;
            RunDirectory) value="$S540_RUN";;
        esac
        /usr/bin/plutil -insert "$key" -string "$value" "$draft"
    done
    /usr/bin/sudo -n /bin/mkdir -p "$S540_ROOT"
    /usr/bin/sudo -n /usr/sbin/chown root:wheel "$S540_ROOT"
    /usr/bin/sudo -n /bin/chmod 755 "$S540_ROOT"
    /usr/bin/sudo -n /usr/bin/ditto "$S540_RUN/kext.manifest" "$S540_ROOT/kext.manifest"
    /usr/bin/sudo -n /usr/bin/ditto "$S540_RUN/app.manifest" "$S540_ROOT/app.manifest"
    /usr/bin/sudo -n /usr/bin/ditto "$draft" "$S540_ROOT/receipt.new"
    /usr/bin/sudo -n /usr/sbin/chown root:wheel "$S540_ROOT/kext.manifest" "$S540_ROOT/app.manifest" "$S540_ROOT/receipt.new"
    /usr/bin/sudo -n /bin/chmod 644 "$S540_ROOT/kext.manifest" "$S540_ROOT/app.manifest" "$S540_ROOT/receipt.new"
    /usr/bin/sudo -n /bin/mv "$S540_ROOT/receipt.new" "$S540_RECEIPT"
    S540_RECEIPT_OURS=1
}

s540_phase() {
    printf 'Stato: %s\n' "$1" >> "$S540_RUN/status.txt"
    if [ "$S540_RECEIPT_OURS" = 1 ]; then
        /usr/bin/sudo -n /usr/bin/plutil -replace State -string "$1" "$S540_RECEIPT"
    fi
}

s540_stage_commit() {
    S540_STAGE=$(/usr/bin/sudo -n /usr/bin/mktemp -d "$S540_ROOT/.stage-$S540_RUN_ID.XXXXXX")
    /usr/bin/sudo -n /bin/chmod 755 "$S540_STAGE"
    local component source destination
    for component in S540HotkeysVPC.kext S540Tasti.app; do
        source="$S540_PACKAGE/assets/$component"
        /usr/bin/sudo -n /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$source" "$S540_STAGE/$component"
        /usr/bin/sudo -n /usr/sbin/chown -R root:wheel "$S540_STAGE/$component"
        /usr/bin/sudo -n /bin/chmod -R go-w "$S540_STAGE/$component"
        /usr/bin/diff -qr "$source" "$S540_STAGE/$component" > "$S540_RUN/stage-$component.diff" || return 1
    done
    if [ ! -e "$S540_KEXT" ]; then
        /usr/bin/sudo -n /bin/mv "$S540_STAGE/S540HotkeysVPC.kext" "$S540_KEXT"
        S540_CREATED_KEXT=1
    fi
    if [ ! -e "$S540_APP" ]; then
        /usr/bin/sudo -n /bin/mv "$S540_STAGE/S540Tasti.app" "$S540_APP"
        S540_CREATED_APP=1
    fi
    s540_owned_paths || return 1
}

s540_stop_agent() {
    if /bin/launchctl print "gui/$S540_UID/$S540_LABEL" > "$S540_RUN/agent-before.txt" 2>&1; then
        /bin/launchctl bootout "gui/$S540_UID/$S540_LABEL" > "$S540_RUN/agent-bootout.log" 2>&1 || return 1
    fi
    # A radio operation may take up to 16 seconds including rollback. Never kill it
    # early or remove the app/driver while an independently opened copy still runs.
    local attempt=0 status
    while [ "$attempt" -lt 30 ]; do
        if /usr/bin/pgrep -u "$S540_UID" -x S540Tasti > "$S540_RUN/app-pids.txt" 2> "$S540_RUN/app-pids.stderr"; then status=0; else status=$?; fi
        [ "$status" != 1 ] || return 0
        [ "$status" = 0 ] || return 1
        attempt=$((attempt + 1))
        /bin/sleep 1
    done
    printf '\nS540 Tasti è ancora attivo: chiudilo dal suo menu prima di ripetere la rimozione.\n' >&2
    return 1
}

s540_rebuild_after_removal() {
    local status
    s540_phase removal_rebuild_pending || return 1
    if /usr/bin/sudo -n /usr/bin/kmutil rebuild > "$S540_RUN/kmutil-removal-rebuild.log" 2>&1; then status=0; else status=$?; fi
    /bin/cat "$S540_RUN/kmutil-removal-rebuild.log"
    if [ "$status" != 0 ]; then
        S540_CACHE_REMOVAL_PENDING=1
        printf '\nFile rimossi e driver scaricato, ma aggiornamento della raccolta kernel non confermato (kmutil: %s).\n' "$status" >&2
        printf 'La ricevuta resta disponibile: consulta kmutil-removal-rebuild.log. Nessun riavvio automatico.\n' >&2
        return 1
    fi
    S540_CACHE_REMOVAL_PENDING=0
    s540_phase removal_reboot_pending
}

s540_unload_owned() {
    local status requested=0
    if s540_loaded "$S540_KEXT_ID"; then status=0; else status=$?; fi
    [ "$status" != 2 ] || return 1
    if [ "$status" = 0 ]; then
        s540_receipt_valid && s540_owned_paths || return 1
        /usr/bin/sudo -n /usr/bin/kmutil unload -b "$S540_KEXT_ID" > "$S540_RUN/kmutil-unload.log" 2>&1 || return 1
        requested=1
    fi
    local attempt
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        if s540_loaded "$S540_KEXT_ID"; then status=0; else status=$?; fi
        [ "$status" != 2 ] || return 1
        if [ "$status" = 1 ]; then
            if s540_service_exists; then status=0; else status=$?; fi
            [ "$status" = 1 ] && return 0
            [ "$status" != 2 ] || return 1
        fi
        /bin/sleep 0.3
    done
    if [ "$requested" = 1 ]; then
        S540_UNLOAD_PENDING=1
        s540_phase removal_reboot_pending || return 1
        printf '\nRichiesta di scaricamento accettata; il driver è ancora attivo. File e ricevuta restano installati.\n' >&2
        printf 'Riavvia normalmente, poi esegui RIPRISTINA-TASTI.command per completare la rimozione.\n' >&2
        return 3
    fi
    return 1
}

s540_rollback_new() {
    [ "$S540_PRESERVE" = 0 ] || return 1
    if [ "$S540_BOOTSTRAPPED" = 1 ]; then s540_stop_agent || return 1; fi
    if [ "$S540_CREATED_KEXT" = 1 ] || [ "$S540_LOADED_HERE" = 1 ]; then s540_unload_owned || return 1; fi
    if [ "$S540_CREATED_AGENT" = 1 ]; then
        if [ -e "$S540_AGENT" ] || [ -L "$S540_AGENT" ]; then
            [ -f "$S540_AGENT" ] && [ ! -L "$S540_AGENT" ] &&
            [ "$(s540_hash "$S540_AGENT")" = "$(s540_plist "$S540_RECEIPT" AgentSHA256 string)" ] || return 1
            /bin/rm -f "$S540_AGENT" || return 1
        fi
        [ ! -e "$S540_AGENT" ] && [ ! -L "$S540_AGENT" ] || return 1
    fi
    if [ "$S540_CREATED_APP" = 1 ]; then
        s540_tree_matches "$S540_APP" "$S540_ROOT/app.manifest" || return 1
        /usr/bin/sudo -n /bin/rm -rf -- "$S540_APP" || return 1
        [ ! -e "$S540_APP" ] && [ ! -L "$S540_APP" ] || return 1
    fi
    if [ "$S540_CREATED_KEXT" = 1 ]; then
        s540_tree_matches "$S540_KEXT" "$S540_ROOT/kext.manifest" || return 1
        /usr/bin/sudo -n /bin/rm -rf -- "$S540_KEXT" || return 1
        [ ! -e "$S540_KEXT" ] && [ ! -L "$S540_KEXT" ] || return 1
        s540_rebuild_after_removal || return 1
    fi
    s540_phase failed_new_files_removed
}

s540_backup_path_valid() {
    case "$1" in "$S540_ROOT/upgrade-v1-"*) ;; *) return 1;; esac
    [ "$1" != "$S540_ROOT/upgrade-v1-" ] && [ "$(/usr/bin/dirname "$1")" = "$S540_ROOT" ]
}

s540_backup_matches() {
    s540_backup_path_valid "$1" && s540_protected "$1" || return 1
    [ "${#2}" = 64 ] || return 1
    case "$2" in *[!0-9a-f]*) return 1;; esac
    s540_tree_manifest "$1" "$S540_RUN/backup-current.manifest" || return 1
    [ "$(s540_hash "$S540_RUN/backup-current.manifest")" = "$2" ]
}

s540_app_upgrade_eligible() {
    local version pinned
    S540_UPGRADE_SOURCE_APP_SHA256=''
    S540_UPGRADE_PRIOR_PATH=''
    S540_UPGRADE_PRIOR_SHA256=''
    [ -d "$S540_APP" ] && [ -d "$S540_KEXT" ] && [ -f "$S540_AGENT" ] || return 1
    version=$(s540_plist "$S540_RECEIPT" Version string) || return 1
    case "$version" in
        0.1.0) S540_UPGRADE_SOURCE_APP_SHA256="$S540_V1_APP_MANIFEST_SHA256"; pinned=upgrade-v1-app.manifest;;
        0.1.1)
            [ "$(s540_plist "$S540_RECEIPT" AppVersion string)" = 0.1.1 ] &&
            [ "$(s540_plist "$S540_RECEIPT" KextVersion string)" = "$S540_KEXT_VERSION" ] || return 1
            S540_UPGRADE_SOURCE_APP_SHA256="$S540_V11_APP_MANIFEST_SHA256"; pinned=upgrade-v1.1-app.manifest;;
        *) return 1;;
    esac
    [ "$(s540_hash "$S540_ROOT/app.manifest")" = "$S540_UPGRADE_SOURCE_APP_SHA256" ] &&
    [ "$(s540_hash "$S540_ROOT/kext.manifest")" = "$S540_V1_KEXT_MANIFEST_SHA256" ] || return 1
    [ "$(s540_hash "$S540_PACKAGE/tools/$pinned")" = "$S540_UPGRADE_SOURCE_APP_SHA256" ] &&
    [ "$(s540_hash "$S540_PACKAGE/tools/upgrade-v1-kext.manifest")" = "$S540_V1_KEXT_MANIFEST_SHA256" ] || return 1
    /usr/bin/cmp -s "$S540_RUN/kext.manifest" "$S540_ROOT/kext.manifest" || return 1
    S540_UPGRADE_PRIOR_PATH=$(s540_plist "$S540_RECEIPT" UpgradeBackupPath string 2>/dev/null || true)
    S540_UPGRADE_PRIOR_SHA256=$(s540_plist "$S540_RECEIPT" UpgradeBackupTreeSHA256 string 2>/dev/null || true)
    if [ -n "$S540_UPGRADE_PRIOR_PATH" ]; then
        [ "$version" = 0.1.1 ] && s540_backup_matches "$S540_UPGRADE_PRIOR_PATH" "$S540_UPGRADE_PRIOR_SHA256" || return 1
    else
        [ -z "$S540_UPGRADE_PRIOR_SHA256" ] || return 1
    fi
}

s540_rollback_app_upgrade() {
    local file current_hash temporary
    [ -n "$S540_UPGRADE_BACKUP" ] && s540_protected "$S540_UPGRADE_BACKUP" || return 1
    [ "$(s540_hash "$S540_UPGRADE_BACKUP/receipt.plist")" = "$S540_UPGRADE_RECEIPT_SHA256" ] &&
    [ "$(s540_hash "$S540_UPGRADE_BACKUP/agent.plist")" = "$S540_UPGRADE_AGENT_SHA256" ] &&
    [ "$(s540_hash "$S540_UPGRADE_BACKUP/app.manifest")" = "$S540_UPGRADE_SOURCE_APP_SHA256" ] &&
    [ "$(s540_hash "$S540_UPGRADE_BACKUP/kext.manifest")" = "$S540_V1_KEXT_MANIFEST_SHA256" ] || return 1
    if [ "$S540_UPGRADE_NEW_APP_INSTALLED" = 1 ]; then s540_stop_agent || return 1; fi
    if [ "$S540_UPGRADE_OLD_APP_MOVED" = 1 ]; then
        if [ -d "$S540_UPGRADE_BACKUP/S540Tasti.app" ]; then
            s540_tree_matches "$S540_UPGRADE_BACKUP/S540Tasti.app" "$S540_UPGRADE_BACKUP/app.manifest" || return 1
            if [ -e "$S540_APP" ] || [ -L "$S540_APP" ]; then
                s540_tree_matches "$S540_APP" "$S540_RUN/app.manifest" && s540_protected "$S540_APP" || return 1
                /usr/bin/sudo -n /bin/rm -rf -- "$S540_APP" || return 1
                [ ! -e "$S540_APP" ] && [ ! -L "$S540_APP" ] || return 1
            fi
            /usr/bin/sudo -n /bin/mv "$S540_UPGRADE_BACKUP/S540Tasti.app" "$S540_APP" || return 1
        else
            # The rename may have failed, or a signal arrived before it ran.
            s540_tree_matches "$S540_APP" "$S540_UPGRADE_BACKUP/app.manifest" || return 1
        fi
        S540_UPGRADE_OLD_APP_MOVED=0
    fi
    if [ -e "$S540_AGENT" ] || [ -L "$S540_AGENT" ]; then
        [ -f "$S540_AGENT" ] && [ ! -L "$S540_AGENT" ] || return 1
        current_hash=$(s540_hash "$S540_AGENT") || return 1
        [ "$current_hash" = "$S540_UPGRADE_AGENT_SHA256" ] ||
        [ "$current_hash" = "$(s540_hash "$S540_RUN/agent.plist")" ] || return 1
    fi
    temporary=$(/usr/bin/mktemp "$HOME/Library/LaunchAgents/.S540-restore.XXXXXX") || return 1
    /bin/cp "$S540_UPGRADE_BACKUP/agent.plist" "$temporary" && /bin/chmod 600 "$temporary" &&
    /bin/mv -f "$temporary" "$S540_AGENT" || return 1
    for file in app.manifest kext.manifest receipt.plist; do
        /usr/bin/sudo -n /usr/bin/ditto "$S540_UPGRADE_BACKUP/$file" "$S540_ROOT/$file" || return 1
        /usr/bin/cmp -s "$S540_UPGRADE_BACKUP/$file" "$S540_ROOT/$file" || return 1
    done
    s540_receipt_valid && s540_owned_paths || return 1
    [ "$(s540_hash "$S540_RECEIPT")" = "$S540_UPGRADE_RECEIPT_SHA256" ] || return 1
    if ! /bin/launchctl print "gui/$S540_UID/$S540_LABEL" >/dev/null 2>&1; then
        /bin/launchctl bootstrap "gui/$S540_UID" "$S540_AGENT" > "$S540_RUN/agent-rollback.log" 2>&1 || return 1
    fi
    S540_UPGRADE_ACTIVE=0
    printf '\nAggiornamento annullato: app, ricevuta e avvio automatico precedenti ripristinati. Driver invariato.\n'
}

s540_upgrade_app() {
    local file agent_stage backup_hash
    S540_OPERATION=upgrade
    s540_take_lock
    s540_receipt_valid && s540_owned_paths && s540_app_upgrade_eligible || s540_fail 'App o backup installati non coincidono con la versione originale 0.1.0/0.1.1: aggiornamento fermato.'
    s540_ready || s540_fail 'Il driver originale non risulta pronto: aggiornamento app fermato senza modificare il driver.'
    s540_make_agent
    S540_UPGRADE_BACKUP="$S540_ROOT/upgrade-v1-$S540_RUN_ID"
    /usr/bin/sudo -n /bin/mkdir "$S540_UPGRADE_BACKUP"
    /usr/bin/sudo -n /bin/chmod 755 "$S540_UPGRADE_BACKUP"
    for file in receipt.plist app.manifest kext.manifest; do
        /usr/bin/sudo -n /usr/bin/ditto "$S540_ROOT/$file" "$S540_UPGRADE_BACKUP/$file"
        /usr/bin/cmp -s "$S540_ROOT/$file" "$S540_UPGRADE_BACKUP/$file" || s540_fail 'Backup della ricevuta non verificato.'
    done
    /usr/bin/sudo -n /usr/bin/ditto "$S540_AGENT" "$S540_UPGRADE_BACKUP/agent.plist"
    /usr/bin/sudo -n /usr/sbin/chown root:wheel "$S540_UPGRADE_BACKUP/agent.plist"
    /usr/bin/sudo -n /bin/chmod 644 "$S540_UPGRADE_BACKUP/agent.plist"
    S540_UPGRADE_RECEIPT_SHA256=$(s540_hash "$S540_RECEIPT")
    S540_UPGRADE_AGENT_SHA256=$(s540_hash "$S540_AGENT")
    [ "$(s540_hash "$S540_UPGRADE_BACKUP/agent.plist")" = "$S540_UPGRADE_AGENT_SHA256" ] || s540_fail 'Backup avvio automatico non verificato.'
    S540_STAGE=$(/usr/bin/sudo -n /usr/bin/mktemp -d "$S540_ROOT/.stage-$S540_RUN_ID.XXXXXX")
    /usr/bin/sudo -n /bin/chmod 755 "$S540_STAGE"
    /usr/bin/sudo -n /usr/bin/ditto --norsrc --noextattr --noacl --noqtn "$S540_PACKAGE/assets/S540Tasti.app" "$S540_STAGE/S540Tasti.app"
    /usr/bin/sudo -n /usr/sbin/chown -R root:wheel "$S540_STAGE/S540Tasti.app"
    /usr/bin/sudo -n /bin/chmod -R go-w "$S540_STAGE/S540Tasti.app"
    s540_tree_matches "$S540_STAGE/S540Tasti.app" "$S540_RUN/app.manifest" || s540_fail 'Copia temporanea app non verificata.'
    /usr/bin/codesign --verify --strict "$S540_STAGE/S540Tasti.app" > "$S540_RUN/app-stage-codesign.log" 2>&1 || s540_fail 'Firma della copia temporanea app non valida.'
    S540_UPGRADE_ACTIVE=1
    s540_stop_agent || s540_fail 'App ancora attiva: aggiornamento annullato.'
    s540_phase app_upgrade_pending
    /usr/bin/sudo -n /usr/bin/plutil -insert PendingAppUpgradeBackupPath -string "$S540_UPGRADE_BACKUP" "$S540_RECEIPT"
    s540_owned_paths || s540_fail 'File installati cambiati durante l’aggiornamento.'
    # Record intent before each rename: an interrupt can arrive when mv returns.
    S540_UPGRADE_OLD_APP_MOVED=1
    /usr/bin/sudo -n /bin/mv "$S540_APP" "$S540_UPGRADE_BACKUP/S540Tasti.app"
    S540_UPGRADE_NEW_APP_INSTALLED=1
    /usr/bin/sudo -n /bin/mv "$S540_STAGE/S540Tasti.app" "$S540_APP"
    s540_tree_matches "$S540_APP" "$S540_RUN/app.manifest" || s540_fail 'App aggiornata non verificata.'
    agent_stage=$(/usr/bin/mktemp "$HOME/Library/LaunchAgents/.S540-update.XXXXXX")
    /bin/cp "$S540_RUN/agent.plist" "$agent_stage"
    /bin/chmod 600 "$agent_stage"
    [ "$(s540_hash "$S540_AGENT")" = "$S540_UPGRADE_AGENT_SHA256" ] || s540_fail 'Avvio automatico cambiato durante l’aggiornamento.'
    /bin/mv -f "$agent_stage" "$S540_AGENT"
    s540_write_receipt
    s540_tree_manifest "$S540_UPGRADE_BACKUP" "$S540_RUN/upgrade-backup.manifest" || s540_fail 'Backup dell’app precedente non verificato.'
    backup_hash=$(s540_hash "$S540_RUN/upgrade-backup.manifest")
    /usr/bin/sudo -n /usr/bin/plutil -insert UpgradeBackupPath -string "$S540_UPGRADE_BACKUP" "$S540_RECEIPT"
    /usr/bin/sudo -n /usr/bin/plutil -insert UpgradeBackupTreeSHA256 -string "$backup_hash" "$S540_RECEIPT"
    if [ -n "$S540_UPGRADE_PRIOR_PATH" ]; then
        /usr/bin/sudo -n /usr/bin/plutil -insert PriorUpgradeBackupPath -string "$S540_UPGRADE_PRIOR_PATH" "$S540_RECEIPT"
        /usr/bin/sudo -n /usr/bin/plutil -insert PriorUpgradeBackupTreeSHA256 -string "$S540_UPGRADE_PRIOR_SHA256" "$S540_RECEIPT"
    fi
    s540_receipt_valid && s540_owned_paths || s540_fail 'Ricevuta aggiornata non verificata.'
    /bin/launchctl bootstrap "gui/$S540_UID" "$S540_AGENT" > "$S540_RUN/agent-bootstrap.log" 2>&1 || s540_fail 'Avvio app aggiornata non riuscito.'
    S540_BOOTSTRAPPED=1
    s540_phase ready
    S540_INSTALL_DONE=1
    S540_UPGRADE_ACTIVE=0
    "$S540_APP_BIN" --status 2> "$S540_RUN/app-status.stderr" || true
    printf '\nS540 Tasti aggiornato alla %s. Driver 0.1.0 invariato; nessun riavvio richiesto dall’aggiornamento.\n' "$S540_APP_VERSION"
    printf 'Backup app precedente: %s\n' "$S540_UPGRADE_BACKUP"
    printf 'Preferenze conservate. Se macOS richiede nuovamente un permesso per l’app aggiornata, abilitalo dal menu dell’app.\n'
    printf 'Prova F4 microfono, F7 radio, F8 webcam e F9 blocco schermo.\n'
}

s540_cleanup() {
    local code=$?
    trap - EXIT
    trap '' INT TERM HUP QUIT
    set +e
    if [ "$S540_OPERATION" = upgrade ] && [ "$code" != 0 ] && [ "$S540_UPGRADE_ACTIVE" = 1 ]; then
        if ! s540_rollback_app_upgrade; then
            printf '\nRipristino dell’app non completato. Nessun intervento sul driver. Backup conservato: %s\n' "$S540_UPGRADE_BACKUP" >&2
            printf 'Non ripetere l’installazione prima di verificare questo backup.\n' >&2
        fi
    fi
    if [ "$S540_OPERATION" = install ] && [ "$code" != 0 ] && [ "$S540_INSTALL_DONE" = 0 ] && [ "$S540_INSTALL_MUTATION_STARTED" = 1 ] && [ "$S540_RECEIPT_OURS" = 1 ]; then
        if ! s540_rollback_new; then
            if [ "$S540_CACHE_REMOVAL_PENDING" != 1 ] && [ "$S540_UNLOAD_PENDING" != 1 ]; then
                s540_phase cleanup_required
                printf '\nRimozione automatica non confermata: verifica i componenti tracciati prima di riavviare.\n'
            fi
        fi
    fi
    if [ -n "$S540_STAGE" ] && [ "$S540_LOCKED" = 1 ]; then
        case "$S540_STAGE" in "$S540_ROOT/.stage-$S540_RUN_ID."*) /usr/bin/sudo -n /bin/rm -rf -- "$S540_STAGE";; esac
    fi
    s540_release_lock
    if [ "$code" != 0 ] && [ -n "$S540_RUN" ]; then printf '\nDettagli conservati in: %s\n' "$S540_RUN"; fi
    exit "$code"
}

s540_traps() {
    trap s540_cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    trap 'exit 131' QUIT
}

s540_install() {
    S540_OPERATION=install
    s540_host
    s540_new_run
    s540_traps
    s540_package
    local exists=0 status load_status rebuild_status phase=driver_pending
    [ ! -e "$S540_ROOT" ] && [ ! -L "$S540_ROOT" ] || exists=1
    if [ "$exists" = 1 ]; then
        s540_receipt_valid && s540_owned_paths || s540_fail 'Esistono componenti o ricevute non verificabili: nessuna sovrascrittura.'
        /usr/bin/cmp -s "$S540_RUN/kext.manifest" "$S540_ROOT/kext.manifest" || s540_fail 'Il driver installato è diverso: nessuna sostituzione automatica.'
        if ! /usr/bin/cmp -s "$S540_RUN/app.manifest" "$S540_ROOT/app.manifest"; then
            S540_OPERATION=upgrade
            s540_app_upgrade_eligible || s540_fail 'App o backup installati diversi dalle versioni originali 0.1.0/0.1.1: nessun aggiornamento automatico.'
            s540_upgrade_app
            return
        fi
    else
        [ ! -e "$S540_KEXT" ] && [ ! -L "$S540_KEXT" ] && [ ! -e "$S540_APP" ] && [ ! -L "$S540_APP" ] && [ ! -e "$S540_AGENT" ] && [ ! -L "$S540_AGENT" ] || s540_fail 'Un percorso di destinazione esiste già: nessuna sovrascrittura.'
        if s540_loaded "$S540_KEXT_ID"; then status=0; else status=$?; fi
        [ "$status" = 1 ] || s540_fail 'Il driver risulta già caricato oppure la verifica non è riuscita.'
        if s540_service_exists; then status=0; else status=$?; fi
        [ "$status" = 1 ] || s540_fail 'Un servizio S540 non tracciato è già presente.'
        if /bin/launchctl print "gui/$S540_UID/$S540_LABEL" >/dev/null 2>&1; then
            s540_fail 'Un LaunchAgent con lo stesso nome è già registrato senza ricevuta.'
        fi
    fi
    s540_competitors
    s540_take_lock
    /usr/bin/sudo -n /usr/bin/kmutil libraries --bundle-path "$S540_PACKAGE/assets/S540HotkeysVPC.kext" --xml > "$S540_RUN/kmutil-libraries.xml" 2> "$S540_RUN/kmutil-libraries.stderr" || s540_fail 'Le dipendenze del driver non sono risolte. Nessun nuovo driver è stato copiato.'
    s540_make_agent
    if [ "$exists" = 0 ]; then s540_write_receipt
    else
        [ "$(s540_hash "$S540_RUN/agent.plist")" = "$(s540_plist "$S540_RECEIPT" AgentSHA256 string)" ] || s540_fail 'Definizione dell’avvio automatico diversa dalla ricevuta esistente.'
    fi
    S540_INSTALL_MUTATION_STARTED=1
    s540_stage_commit
    s540_phase load_requested
    if s540_loaded "$S540_KEXT_ID"; then status=0; else status=$?; fi
    [ "$status" != 2 ] || s540_fail 'Stato del driver sconosciuto: caricamento fermato.'
    if [ "$status" = 1 ]; then
        set +e
        /usr/bin/sudo -n /usr/bin/kmutil load -p "$S540_KEXT" > "$S540_RUN/kmutil-load.log" 2>&1
        load_status=$?
        set -e
        /bin/cat "$S540_RUN/kmutil-load.log"
        case "$load_status" in
            0) phase=reboot_pending;;
            27) phase=approval_pending;;
            28)
                set +e
                /usr/bin/sudo -n /usr/bin/kmutil rebuild > "$S540_RUN/kmutil-rebuild.log" 2>&1
                rebuild_status=$?
                set -e
                /bin/cat "$S540_RUN/kmutil-rebuild.log"
                case "$rebuild_status" in 0) phase=reboot_pending;; 27|28) phase=approval_pending;; *) s540_fail 'Ricostruzione non completata; consulta il log kmutil.';; esac;;
            *)
                if s540_loaded "$S540_KEXT_ID"; then S540_LOADED_HERE=1; else status=$?; [ "$status" != 2 ] || S540_PRESERVE=1; fi
                s540_fail 'Richiesta di caricamento fallita. Nessun riavvio automatico; errore kmutil conservato.';;
        esac
        if s540_loaded "$S540_KEXT_ID"; then status=0; S540_LOADED_HERE=1; else status=$?; fi
        if [ "$status" = 2 ]; then
            S540_PRESERVE=1
            s540_fail 'La richiesta è terminata, ma lo stato del driver non è leggibile: file conservati, app non avviata.'
        fi
    fi
    local attempt
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        if s540_ready; then phase=ready; break; fi
        [ "$S540_DRIVER_STATE" != Fault ] || s540_fail 'Il driver ha segnalato un errore di inizializzazione. L’app non viene avviata.'
        [ "$status" = 0 ] || break
        /bin/sleep 0.25
    done
    if [ ! -e "$S540_AGENT" ]; then
        [ ! -L "$HOME/Library/LaunchAgents" ] || s540_fail 'LaunchAgents è un collegamento: operazione fermata.'
        /bin/mkdir -p "$HOME/Library/LaunchAgents"
        local agent_stage
        agent_stage=$(/usr/bin/mktemp "$HOME/Library/LaunchAgents/.S540-agent.XXXXXX")
        /bin/cp "$S540_RUN/agent.plist" "$agent_stage"
        /bin/chmod 600 "$agent_stage"
        if ! /bin/ln "$agent_stage" "$S540_AGENT"; then
            /bin/rm -f "$agent_stage"
            s540_fail 'La destinazione LaunchAgent è comparsa durante l’installazione.'
        fi
        /bin/rm -f "$agent_stage"
        S540_CREATED_AGENT=1
    fi
    s540_owned_paths || s540_fail 'Verifica dei componenti installati non superata.'
    s540_stop_agent || s540_fail 'Impossibile aggiornare la sola sessione dell’app S540.'
    /bin/launchctl bootstrap "gui/$S540_UID" "$S540_AGENT" > "$S540_RUN/agent-bootstrap.log" 2>&1 || s540_fail 'Avvio automatico dell’app non riuscito.'
    S540_BOOTSTRAPPED=1
    s540_phase "$phase"
    S540_INSTALL_DONE=1
    "$S540_APP_BIN" --status 2> "$S540_RUN/app-status.stderr" || true
    if [ "$phase" = ready ]; then
        printf '\nInstallazione completata. S540 Tasti è nella barra dei menu.\n'
        printf 'Prova funzionale: F4 microfono, F7 radio, F8 webcam e F9 blocco schermo.\n'
        printf 'Se F9 richiede permessi, usa la relativa voce nel menu dell’app.\n'
    else
        printf '\nFile e avvio automatico installati; driver ancora in attesa (%s).\n' "$phase"
        printf 'Segui l’eventuale richiesta macOS in Privacy e sicurezza e riavvia normalmente quando richiesto.\n'
        printf 'L’app attende il driver. Dopo il riavvio verifica F4, F7, F8 e F9 una volta.\n'
    fi
}

s540_verify() {
    S540_OPERATION=verify
    s540_host
    s540_new_run
    s540_receipt_valid && s540_owned_paths || s540_fail 'Installazione assente, modificata o non appartenente a questa ricevuta.'
    local state status
    state=$(s540_plist "$S540_RECEIPT" State string)
    printf 'Ricevuta: %s\n' "$state"
    if s540_loaded "$S540_KEXT_ID"; then printf 'Driver caricato.\n'; else status=$?; [ "$status" != 2 ] || s540_fail 'Impossibile leggere lo stato del driver.'; printf 'Driver non ancora caricato.\n'; fi
    if s540_ready; then printf 'Servizio VPC pronto.\n'
    elif [ "$S540_DRIVER_STATE" = Fault ]; then printf 'Il servizio VPC segnala un errore di inizializzazione.\n'
    else printf 'Servizio VPC in attesa: controlla eventuale approvazione o riavvio richiesto da macOS.\n'; fi
    /bin/launchctl print "gui/$S540_UID/$S540_LABEL" > "$S540_RUN/launchagent.txt" 2>&1 && printf 'Avvio automatico registrato.\n' || printf 'Avvio automatico non registrato.\n'
    [ -x "$S540_APP_BIN" ] || s540_fail 'App non presente.'
    "$S540_APP_BIN" --status
    printf '\nLa verifica non ha modificato microfono, radio o webcam.\n'
}

s540_remove_upgrade_backup() {
    local prefix backup expected other='' index=0
    local backups=()
    # Validate the complete bounded chain before deleting either backup.
    for prefix in Upgrade PriorUpgrade; do
        backup=$(s540_plist "$S540_RECEIPT" "${prefix}BackupPath" string 2>/dev/null || true)
        expected=$(s540_plist "$S540_RECEIPT" "${prefix}BackupTreeSHA256" string 2>/dev/null || true)
        if [ -z "$backup" ]; then [ -z "$expected" ] || return 1; continue; fi
        s540_backup_path_valid "$backup" && [ "$backup" != "$other" ] || return 1
        if [ -e "$backup" ] || [ -L "$backup" ]; then s540_backup_matches "$backup" "$expected" || return 1; fi
        backups[$index]="$backup"; index=$((index + 1)); other="$backup"
    done
    [ "$index" != 0 ] || return 0
    for backup in "${backups[@]}"; do
        /usr/bin/sudo -n /bin/rm -rf -- "$backup" || return 1
        [ ! -e "$backup" ] && [ ! -L "$backup" ] || return 1
    done
}

s540_restore() {
    S540_OPERATION=restore
    s540_host
    s540_new_run
    s540_traps
    s540_receipt_valid && s540_owned_paths || s540_fail 'Ricevuta o file non verificabili: nessuna rimozione.'
    s540_take_lock
    s540_stop_agent || s540_fail 'L’app non è stata fermata: nessun componente viene eliminato.'
    s540_unload_owned || s540_fail 'Rimozione non completata. I file restano installati; consulta lo stato e kmutil-unload.log.'
    # Recheck exact manifests immediately before each deletion; no unrelated path is removed.
    s540_owned_paths || s540_fail 'Un componente è cambiato durante la rimozione: operazione fermata.'
    if [ -e "$S540_AGENT" ]; then /bin/rm -f "$S540_AGENT"; fi
    [ ! -e "$S540_AGENT" ] && [ ! -L "$S540_AGENT" ] || s540_fail 'Rimozione LaunchAgent non confermata.'
    if [ -e "$S540_APP" ]; then /usr/bin/sudo -n /bin/rm -rf -- "$S540_APP"; fi
    [ ! -e "$S540_APP" ] && [ ! -L "$S540_APP" ] || s540_fail 'Rimozione app non confermata.'
    if [ -e "$S540_KEXT" ]; then /usr/bin/sudo -n /bin/rm -rf -- "$S540_KEXT"; fi
    [ ! -e "$S540_KEXT" ] && [ ! -L "$S540_KEXT" ] || s540_fail 'Rimozione driver non confermata.'
    s540_rebuild_after_removal || s540_fail 'Rimozione da completare: aggiornamento della raccolta kernel non confermato; ricevuta conservata.'
    s540_remove_upgrade_backup || s540_fail 'Componenti rimossi, ma backup aggiornamento non verificabile: backup e ricevuta conservati.'
    /usr/bin/sudo -n /bin/rm -f "$S540_RECEIPT" "$S540_ROOT/kext.manifest" "$S540_ROOT/app.manifest"
    /usr/bin/sudo -n /bin/rmdir "$S540_ROOT" 2>/dev/null || true
    printf '\nS540 Tasti rimosso. Gli altri driver, l’EFI e il boot non sono stati modificati.\n'
    printf 'La raccolta kernel è stata aggiornata; riavvia normalmente per completare la rimozione dalla cache di avvio.\n'
}
