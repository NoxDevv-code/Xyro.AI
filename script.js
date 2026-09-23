// ======================================================
// XYRO.AI V2.1
// SCRIPT PRINCIPAL
// ======================================================

"use strict";

// ======================================================
// CONFIGURATION
// ======================================================

const APP_NAME = "Xyro.AI";

const SESSION_KEY = "xyro_session_id";
const SETTINGS_KEY = "xyro_settings";
const THEME_KEY = "xyro_theme";
const PROJECT_KEY = "xyro_project";

// ======================================================
// DOM
// ======================================================

const input = document.getElementById("msg");
const mediaInput = document.getElementById("media-input");
const attachMedia = document.getElementById("attach-media");
const mediaPreview = document.getElementById("media-preview");
let pendingMedia = null;
const send = document.getElementById("send");
const chatArea = document.getElementById("chat-area");

// ======================================================
// SESSION
// ======================================================

function creerSessionId() {
    if (
        window.crypto &&
        typeof window.crypto.randomUUID === "function"
    ) {
        return window.crypto.randomUUID();
    }

    return (
        Date.now().toString(36) +
        "-" +
        Math.random().toString(36).slice(2)
    );
}

let sessionId =
    localStorage.getItem(SESSION_KEY);

if (!sessionId) {
    sessionId = creerSessionId();

    localStorage.setItem(
        SESSION_KEY,
        sessionId
    );
}

// ======================================================
// PARAMÈTRES
// ======================================================

const defaultSettings = {
    mode: "normal",
    response_style: "court",
    personality: "cool",
    autoRead: true
};

let settings = {
    ...defaultSettings
};

try {
    const saved =
        localStorage.getItem(SETTINGS_KEY);

    if (saved) {
        settings = {
            ...defaultSettings,
            ...JSON.parse(saved)
        };
    }
} catch (error) {
    console.error(
        "Erreur paramètres :",
        error
    );

    settings = {
        ...defaultSettings
    };
}

// ======================================================
// OUTILS GÉNÉRAUX
// ======================================================

function $(selector) {
    return document.querySelector(selector);
}

function $$(selector) {
    return document.querySelectorAll(selector);
}

function escapeHTML(text) {
    const div =
        document.createElement("div");

    div.textContent =
        String(text ?? "");

    return div.innerHTML;
}

function scrollChat() {
    if (!chatArea) return;

    chatArea.scrollTop =
        chatArea.scrollHeight;
}

function afficherNotification(message) {
    const container =
        document.getElementById(
            "toast-container"
        );

    if (!container) {
        console.log(message);
        return;
    }

    const toast =
        document.createElement("div");

    toast.className = "toast";
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform =
            "translateY(8px)";

        setTimeout(() => {
            toast.remove();
        }, 250);
    }, 3000);
}

function fermerModal(id) {
    const modal =
        document.getElementById(id);

    if (modal) {
        modal.classList.remove("open");
    }
}

// ======================================================
// COMPTE
// ======================================================

async function chargerCompte() {
    try {
        const response =
            await fetch("/api/me");

        if (response.status === 401) {
            window.location.href =
                "/login";

            return null;
        }

        if (!response.ok) {
            return null;
        }

        const data =
            await response.json();

        if (!data.user) {
            return data;
        }

        const username =
            data.user.username ||
            "Utilisateur";

        const avatar =
            username
                .slice(0, 2)
                .toUpperCase();

        const topAvatar =
            document.querySelector(
                ".avatar"
            );

        const topUsername =
            document.getElementById(
                "username-top"
            );

        const settingsUsername =
            document.getElementById(
                "settings-username"
            );

        const settingsAvatar =
            document.getElementById(
                "settings-avatar"
            );

        const publicId =
            document.getElementById(
                "settings-public-id"
            );

        if (topAvatar) {
            topAvatar.textContent =
                avatar;
        }

        if (topUsername) {
            topUsername.textContent =
                username;
        }

        if (settingsUsername) {
            settingsUsername.textContent =
                username;
        }

        if (settingsAvatar) {
            settingsAvatar.textContent =
                avatar;
        }

        if (publicId) {
            publicId.textContent =
                data.user.public_id
                    ? `ID : ${data.user.public_id}`
                    : "ID Xyro";
        }

        return data;

    } catch (error) {
        console.error(
            "Erreur compte :",
            error
        );

        return null;
    }
}

// ======================================================
// DÉCONNEXION
// ======================================================

async function deconnexion() {
    try {
        await fetch(
            "/api/logout",
            {
                method: "POST"
            }
        );
    } catch (error) {
        console.error(
            "Erreur déconnexion :",
            error
        );
    }

    localStorage.removeItem(
        SESSION_KEY
    );

    localStorage.removeItem(
        PROJECT_KEY
    );

    window.location.href =
        "/login";
}

// ======================================================
// NAVIGATION
// ======================================================

const viewTitles = {
    home: "Accueil",
    chat: "Chat",
    projects: "Projets",
    memory: "Mémoire",
    tools: "Outils",
    internet: "Internet",
    voice: "Voix",
    settings: "Paramètres"
};

function ouvrirVue(viewName) {
    const view =
        document.getElementById(
            `view-${viewName}`
        );

    if (!view) {
        console.warn(
            "Vue introuvable :",
            viewName
        );

        return;
    }

    $$(".view").forEach(
        element => {
            element.classList.remove(
                "active"
            );
        }
    );

    view.classList.add("active");

    $$(".nav-btn[data-view]")
        .forEach(button => {
            button.classList.toggle(
                "active",
                button.dataset.view ===
                    viewName
            );
        });

    const title =
        document.getElementById(
            "topbar-title"
        );

    if (title) {
        title.textContent =
            viewTitles[viewName] ||
            APP_NAME;
    }

    if (viewName === "chat") {
        setTimeout(() => {
            input?.focus();
        }, 100);
    }

    if (viewName === "memory") {
        chargerMemoire();
    }

    if (viewName === "projects") {
        chargerProjets();
    }

    if (viewName === "settings") {
        chargerParametresUI();
    }
}

// ======================================================
// NOUVELLE DISCUSSION
// ======================================================

function nouvelleDiscussion() {
    sessionId =
        creerSessionId();

    localStorage.setItem(
        SESSION_KEY,
        sessionId
    );

    if (chatArea) {
        chatArea.innerHTML = `
            <div class="welcome-chat">

                <div class="welcome-icon">
                    XY
                </div>

                <h2>
                    Nouvelle discussion 👋
                </h2>

                <p>
                    Commence une conversation
                    avec <strong>Xyro.AI</strong>.
                </p>

            </div>
        `;
    }

    ouvrirVue("chat");

    afficherNotification(
        "Nouvelle discussion créée."
    );
}

// ======================================================
// MESSAGE UTILISATEUR
// ======================================================

function ajouterMessageUser(message, attachment = null) {
    if (!chatArea) return;

    const welcome = chatArea.querySelector(".welcome-chat");
    if (welcome) welcome.remove();

    const element = document.createElement("div");
    element.className = "message user";

    if (message) {
        const text = document.createElement("div");
        text.textContent = message;
        element.appendChild(text);
    }

    if (attachment?.url) {
        if (attachment.kind === "image") {
            const img = document.createElement("img");
            img.className = "message-media image";
            img.src = attachment.url;
            img.alt = attachment.name || "Image jointe";
            img.loading = "lazy";
            element.appendChild(img);
        } else if (attachment.kind === "video") {
            const video = document.createElement("video");
            video.className = "message-media video";
            video.src = attachment.url;
            video.controls = true;
            video.preload = "metadata";
            element.appendChild(video);
        }
    }

    chatArea.appendChild(element);
    scrollChat();
}

// ======================================================
// MESSAGE XYRO
// ======================================================

function ajouterMessageBot(
    message,
    options = {}
) {
    if (!chatArea) return;

    const {
        speak = true
    } = options;

    const welcome =
        chatArea.querySelector(
            ".welcome-chat"
        );

    if (welcome) {
        welcome.remove();
    }

    const element =
        document.createElement("div");

    element.className =
        "message bot";

    const title =
        document.createElement("div");

    title.className =
        "bot-title";

    title.innerHTML = `
        <span class="mini-bn">
            XY
        </span>

        Xyro.AI

        <i>
            ● En ligne
        </i>
    `;

    const content =
        afficherMessageFormate(
            message
        );

    element.appendChild(
        title
    );

    element.appendChild(
        content
    );

    chatArea.appendChild(
        element
    );

    scrollChat();

    if (
        speak &&
        settings.autoRead &&
        "speechSynthesis" in window
    ) {
        lireTexte(
            nettoyerTextePourVoix(
                message
            )
        );
    }
}

// ======================================================
// CHARGEMENT
// ======================================================

function ajouterChargement() {
    if (!chatArea) {
        return null;
    }

    const element =
        document.createElement("div");

    element.className =
        "message bot xyro-loading";

    element.innerHTML = `
        <div class="bot-title">

            <span class="mini-bn">
                XY
            </span>

            Xyro.AI

            <i>
                ● réfléchit...
            </i>

        </div>

        <div class="thinking-animation">

            <span>🧠</span>

            <span>
                Xyro réfléchit
            </span>

            <div class="thinking-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>

        </div>
    `;

    chatArea.appendChild(
        element
    );

    scrollChat();

    return element;
}

// ======================================================
// PHOTOS / VIDÉOS
// ======================================================

function clearMediaSelection() {
    pendingMedia = null;
    if (mediaInput) mediaInput.value = "";
    if (mediaPreview) {
        mediaPreview.innerHTML = "";
        mediaPreview.classList.add("hidden");
    }
}

function renderMediaPreview(attachment) {
    if (!mediaPreview) return;
    mediaPreview.classList.remove("hidden");
    mediaPreview.innerHTML = "";

    const wrap = document.createElement("div");
    wrap.className = "media-preview-card";

    if (attachment.kind === "image") {
        const img = document.createElement("img");
        img.src = attachment.localUrl;
        img.alt = attachment.name;
        wrap.appendChild(img);
    } else {
        const video = document.createElement("video");
        video.src = attachment.localUrl;
        video.muted = true;
        video.playsInline = true;
        wrap.appendChild(video);
    }

    const info = document.createElement("span");
    info.textContent = attachment.name;
    wrap.appendChild(info);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "media-remove";
    remove.textContent = "×";
    remove.title = "Retirer";
    remove.onclick = clearMediaSelection;
    wrap.appendChild(remove);

    mediaPreview.appendChild(wrap);
}

async function choisirMedia(file) {
    if (!file) return;
    if (file.size > 25 * 1024 * 1024) {
        afficherNotification("Fichier trop volumineux : 25 Mo maximum.");
        clearMediaSelection();
        return;
    }

    const kind = file.type.startsWith("image/") ? "image" :
        file.type.startsWith("video/") ? "video" : null;
    if (!kind) {
        afficherNotification("Choisis une photo ou une vidéo.");
        return;
    }

    const localUrl = URL.createObjectURL(file);
    pendingMedia = {
        kind,
        name: file.name,
        localUrl,
        file
    };
    renderMediaPreview(pendingMedia);

    try {
        const form = new FormData();
        form.append("file", file);
        const response = await fetch("/api/upload-media", {
            method: "POST",
            body: form
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "Upload impossible.");

        pendingMedia = {
            ...pendingMedia,
            url: data.url,
            data_url: data.data_url || null
        };
        renderMediaPreview(pendingMedia);
        afficherNotification(kind === "image" ? "Photo ajoutée 📷" : "Vidéo ajoutée 🎥");
    } catch (error) {
        console.error("Upload média :", error);
        clearMediaSelection();
        afficherNotification("Impossible d'envoyer ce fichier.");
    }
}

if (attachMedia && mediaInput) {
    attachMedia.addEventListener("click", () => mediaInput.click());
    mediaInput.addEventListener("change", () => choisirMedia(mediaInput.files?.[0]));
}

// ======================================================
// ENVOYER UN MESSAGE
// ======================================================

async function envoyer(
    messageForce = null
) {
    if (!input || !send) {
        return;
    }

    const message = messageForce ?? input.value.trim();

    if ((!message && !pendingMedia) || send.disabled) {
        return;
    }

    const attachment = pendingMedia;
    input.value = "";
    ajusterHauteurInput();
    send.disabled = true;
    ouvrirVue("chat");
    ajouterMessageUser(message, attachment);
    clearMediaSelection();

    const loading =
        ajouterChargement();

    try {
        const response =
            await fetch(
                "/chat",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        message,
                        attachment: attachment ? {
                            kind: attachment.kind,
                            url: attachment.url,
                            data_url: attachment.data_url || null
                        } : null,

                        session_id:
                            sessionId,

                        mode:
                            settings.mode,

                        response_style:
                            settings.response_style,

                        personality:
                            settings.personality,

                        project:
                            window.xyroProject ||
                            ""
                    })
                }
            );

        const data =
            await response
                .json()
                .catch(
                    () => ({})
                );

        loading?.remove();

        if (
            response.status === 401
        ) {
            window.location.href =
                "/login";

            return;
        }

        if (
            response.status === 429
        ) {
            ajouterMessageBot(
                data.error ||
                "🟠 Xyro est temporairement limité par l'API. Réessaie dans quelques minutes."
            );

            return;
        }

        if (!response.ok) {
            ajouterMessageBot(
                data.response ||
                data.error ||
                "⚠️ Une erreur est survenue."
            );

            return;
        }

        if (data.session_id) {
            sessionId =
                data.session_id;

            localStorage.setItem(
                SESSION_KEY,
                sessionId
            );
        }

        ajouterMessageBot(
            data.response ||
            data.output ||
            "Je n'ai pas reçu de réponse."
        );

    } catch (error) {
        console.error(
            "Erreur Xyro :",
            error
        );

        loading?.remove();

        ajouterMessageBot(
            "⚠️ Impossible de contacter Xyro pour le moment."
        );

    } finally {
        send.disabled = false;

        input.focus();
    }
}

function envoyerCommande(
    message
) {
    if (!message) return;

    ouvrirVue("chat");

    envoyer(message);
}

// ======================================================
// CHAMP DE MESSAGE
// ======================================================

function ajusterHauteurInput() {
    if (!input) return;

    input.style.height =
        "auto";

    input.style.height =
        Math.min(
            input.scrollHeight,
            150
        ) + "px";
}

if (input) {
    input.addEventListener(
        "keydown",
        event => {
            if (
                event.key ===
                    "Enter" &&
                !event.shiftKey
            ) {
                event.preventDefault();

                envoyer();
            }
        }
    );

    input.addEventListener(
        "input",
        ajusterHauteurInput
    );
}

// ======================================================
// HISTORIQUE
// ======================================================

async function chargerHistorique() {
    if (!chatArea) return;

    try {
        const response =
            await fetch(
                `/history?session_id=${encodeURIComponent(
                    sessionId
                )}`
            );

        if (
            response.status === 401
        ) {
            window.location.href =
                "/login";

            return;
        }

        if (!response.ok) {
            return;
        }

        const data =
            await response.json();

        const messages =
            data.messages ||
            data.history ||
            [];

        if (
            !Array.isArray(
                messages
            )
        ) {
            return;
        }

        chatArea.innerHTML =
            "";

        if (
            messages.length === 0
        ) {
            chatArea.innerHTML = `
                <div class="welcome-chat">

                    <div class="welcome-icon">
                        XY
                    </div>

                    <h2>
                        Nouvelle discussion 👋
                    </h2>

                    <p>
                        Commence une conversation
                        avec <strong>Xyro.AI</strong>.
                    </p>

                </div>
            `;

            return;
        }

        messages.forEach(
            item => {
                if (
                    item.role ===
                    "user"
                ) {
                    ajouterMessageUser(
                        item.content
                    );
                }

                if (
                    item.role ===
                        "assistant" ||
                    item.role ===
                        "bot"
                ) {
                    ajouterMessageBot(
                        item.content,
                        {
                            speak: false
                        }
                    );
                }
            }
        );

    } catch (error) {
        console.error(
            "Erreur historique :",
            error
        );
    }
}

// ======================================================
// CODE
// ======================================================

function detecterLangage(code) {
    if (
        /\b(def|import|print|class|self|elif)\b/
            .test(code)
    ) {
        return "Python";
    }

    if (
        /\b(const|let|var|function|console\.log|document\.)\b/
            .test(code)
    ) {
        return "JavaScript";
    }

    if (
        /<!DOCTYPE html>|<html|<body|<div|<section|<header/i
            .test(code)
    ) {
        return "HTML";
    }

    if (
        /\b(color|background|margin|padding|display|font-size)\s*:/
            .test(code)
    ) {
        return "CSS";
    }

    if (
        /\b(SELECT|INSERT|UPDATE|DELETE)\b/i
            .test(code)
    ) {
        return "SQL";
    }

    if (
        /\b(public|private|static|void|System\.out)\b/
            .test(code)
    ) {
        return "Java";
    }

    if (
        /#include\s*<|std::/
            .test(code)
    ) {
        return "C++";
    }

    return "Code";
}

function coloriserCode(
    code,
    langage
) {
    let result =
        escapeHTML(code);

    result =
        result.replace(
            /(["'`])(?:\\.|(?!\1).)*?\1/g,
            '<span class="code-value">$&</span>'
        );

    result =
        result.replace(
            /\b(def|class|import|from|return|if|else|elif|for|while|in|True|False|None|const|let|var|function|new|async|await|public|private|static|void|SELECT|FROM|WHERE|INSERT|UPDATE|DELETE)\b/g,
            '<span class="code-keyword">$1</span>'
        );

    result =
        result.replace(
            /\b([a-zA-Z_$][\w$]*)\s*(?=\()/g,
            '<span class="code-function">$1</span>'
        );

    if (
        langage === "HTML"
    ) {
        result =
            result.replace(
                /(&lt;\/?)([\w-]+)/g,
                '$1<span class="code-tag">$2</span>'
            );
    }

    return result;
}

function obtenirExtension(
    langage
) {
    switch (
        langage.toLowerCase()
    ) {
        case "python":
            return "py";

        case "javascript":
            return "js";

        case "html":
            return "html";

        case "css":
            return "css";

        case "sql":
            return "sql";

        case "java":
            return "java";

        case "c++":
            return "cpp";

        default:
            return "txt";
    }
}

function creerBlocCode(
    code,
    langage
) {
    const wrapper =
        document.createElement(
            "div"
        );

    wrapper.className =
        "xyro-code";

    const header =
        document.createElement(
            "div"
        );

    header.className =
        "code-header";

    const language =
        document.createElement(
            "span"
        );

    language.className =
        "code-language";

    language.textContent =
        langage;

    const actions =
        document.createElement(
            "div"
        );

    actions.className =
        "code-actions";

    const copyButton =
        document.createElement(
            "button"
        );

    copyButton.className =
        "code-action";

    copyButton.textContent =
        "📋 Copier";

    const downloadButton =
        document.createElement(
            "button"
        );

    downloadButton.className =
        "code-action";

    downloadButton.textContent =
        "⬇️ Télécharger";

    actions.append(
        copyButton,
        downloadButton
    );

    header.append(
        language,
        actions
    );

    const codeWrapper =
        document.createElement(
            "div"
        );

    codeWrapper.className =
        "code-wrapper";

    const lineNumbers =
        document.createElement(
            "div"
        );

    lineNumbers.className =
        "code-line-numbers";

    const codeContent =
        document.createElement(
            "pre"
        );

    codeContent.className =
        "code-content";

    const lines =
        code.split("\n");

    lineNumbers.innerHTML =
        lines
            .map(
                (_, index) =>
                    index + 1
            )
            .join("<br>");

    codeContent.innerHTML =
        coloriserCode(
            code,
            langage
        );

    codeWrapper.append(
        lineNumbers,
        codeContent
    );

    wrapper.append(
        header,
        codeWrapper
    );

    copyButton.addEventListener(
        "click",
        async () => {
            try {
                await navigator.clipboard
                    .writeText(code);

                copyButton.textContent =
                    "✅ Copié !";

                setTimeout(() => {
                    copyButton.textContent =
                        "📋 Copier";
                }, 1500);

            } catch {
                afficherNotification(
                    "Impossible de copier le code."
                );
            }
        }
    );

    downloadButton.addEventListener(
        "click",
        () => {
            const extension =
                obtenirExtension(
                    langage
                );

            const blob =
                new Blob(
                    [code],
                    {
                        type:
                            "text/plain;charset=utf-8"
                    }
                );

            const url =
                URL.createObjectURL(
                    blob
                );

            const link =
                document.createElement(
                    "a"
                );

            link.href =
                url;

            link.download =
                `xyro-code.${extension}`;

            document.body.appendChild(
                link
            );

            link.click();

            link.remove();

            URL.revokeObjectURL(
                url
            );
        }
    );

    return wrapper;
}

function afficherMessageFormate(
    message
) {
    const container =
        document.createElement(
            "div"
        );

    container.className =
        "message-text";

    const regex =
        /```([\w#+.-]+)?\n?([\s\S]*?)```/g;

    let dernierIndex = 0;
    let match;

    while (
        (match =
            regex.exec(message)) !== null
    ) {
        const avant =
            message.slice(
                dernierIndex,
                match.index
            );

        if (avant.trim()) {
            const text =
                document.createElement(
                    "div"
                );

            text.innerHTML =
                escapeHTML(
                    avant
                ).replace(
                    /\n/g,
                    "<br>"
                );

            container.appendChild(
                text
            );
        }

        const code =
            match[2].trim();

        const langage =
            match[1] ||
            detecterLangage(
                code
            );

        container.appendChild(
            creerBlocCode(
                code,
                langage
            )
        );

        dernierIndex =
            regex.lastIndex;
    }

    const reste =
        message.slice(
            dernierIndex
        );

    if (reste.trim()) {
        const text =
            document.createElement(
                "div"
            );

        text.innerHTML =
            escapeHTML(
                reste
            ).replace(
                /\n/g,
                "<br>"
            );

        container.appendChild(
            text
        );
    }

    return container;
}

// ======================================================
// IMAGE
// ======================================================

function ouvrirCreateurImage() {
    ouvrirVue("chat");

    const ancien =
        document.getElementById(
            "image-creator"
        );

    if (ancien) {
        ancien.remove();
    }

    const element =
        document.createElement(
            "div"
        );

    element.id =
        "image-creator";

    element.className =
        "message bot";

    element.innerHTML = `
        <div class="bot-title">

            <span class="mini-bn">
                XY
            </span>

            Xyro.AI

            <i>
                ● Générateur d'image
            </i>

        </div>

        <div>
            🎨 Décris l'image que tu veux créer :
        </div>

        <textarea
            id="image-prompt"
            placeholder="Ex : un robot XY dans une ville futuriste..."
            style="
                width:100%;
                min-height:100px;
                margin-top:12px;
                padding:12px;
                border-radius:10px;
                resize:vertical;
            "
        ></textarea>

        <div
            style="
                display:flex;
                gap:8px;
                margin-top:10px;
            "
        >

            <button
                id="create-image-btn"
                class="primary-btn"
            >
                🎨 Créer
            </button>

            <button
                id="cancel-image-btn"
                class="secondary-btn"
            >
                Annuler
            </button>

        </div>
    `;

    chatArea.appendChild(
        element
    );

    const prompt =
        document.getElementById(
            "image-prompt"
        );

    document.getElementById(
        "create-image-btn"
    ).onclick = () => {
        const value =
            prompt.value.trim();

        if (!value) {
            prompt.focus();
            return;
        }

        element.remove();

        genererImage(value);
    };

    document.getElementById(
        "cancel-image-btn"
    ).onclick = () => {
        element.remove();
    };

    prompt.focus();

    scrollChat();
}

async function genererImage(
    prompt
) {
    ajouterMessageUser(
        "🖼️ Crée cette image : " +
        prompt
    );

    const loading =
        ajouterChargement();

    try {
        const response =
            await fetch(
                "/generate-image",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        prompt
                    })
                }
            );

        const data =
            await response
                .json()
                .catch(
                    () => ({})
                );

        loading?.remove();

        if (!response.ok) {
            ajouterMessageBot(
                "⚠️ " +
                (
                    data.error ||
                    "Impossible de créer l'image."
                )
            );

            return;
        }

        if (!data.image) {
            ajouterMessageBot(
                "⚠️ Xyro n'a reçu aucune image."
            );

            return;
        }

        afficherImage(
            data.image
        );

    } catch (error) {
        console.error(
            "Erreur image :",
            error
        );

        loading?.remove();

        ajouterMessageBot(
            "⚠️ La génération d'image a échoué."
        );
    }
}

function afficherImage(
    base64
) {
    const element =
        document.createElement(
            "div"
        );

    element.className =
        "message bot";

    element.innerHTML = `
        <div class="bot-title">

            <span class="mini-bn">
                XY
            </span>

            Xyro.AI

            <i>
                ● Image créée
            </i>

        </div>
    `;

    const image =
        document.createElement(
            "img"
        );

    image.src =
        "data:image/png;base64," +
        base64;

    image.alt =
        "Image générée par Xyro.AI";

    image.style.maxWidth =
        "100%";

    image.style.borderRadius =
        "14px";

    image.style.marginTop =
        "10px";

    element.appendChild(
        image
    );

    chatArea.appendChild(
        element
    );

    scrollChat();
}

// ======================================================
// MÉMOIRE
// ======================================================

async function chargerMemoire() {
    const container =
        document.getElementById(
            "memory-container"
        );

    if (!container) return;

    try {
        const response =
            await fetch(
                "/memory"
            );

        if (
            response.status === 401
        ) {
            window.location.href =
                "/login";

            return;
        }

        const data =
            await response.json();

        const memories =
            data.memories ||
            data.memory ||
            [];

        container.innerHTML =
            "";

        if (
            !Array.isArray(
                memories
            ) ||
            memories.length === 0
        ) {
            container.innerHTML = `
                <div class="empty-state">

                    <div>🧠</div>

                    <h3>
                        Ta mémoire est vide
                    </h3>

                    <p>
                        Dis à Xyro de retenir
                        quelque chose pendant une conversation.
                    </p>

                </div>
            `;

            mettreAJourMemoireDroite(
                0
            );

            return;
        }

        memories.forEach(
            memory => {
                const content =
                    typeof memory ===
                    "string"
                        ? memory
                        : (
                            memory.content ||
                            memory.memory ||
                            ""
                        );

                const item =
                    document.createElement(
                        "div"
                    );

                item.className =
                    "memory-item";

                item.innerHTML = `
                    <div class="memory-item-icon">
                        🧠
                    </div>

                    <div class="memory-item-content">

                        <strong>
                            Souvenir enregistré
                        </strong>

                        <p>
                            ${escapeHTML(content)}
                        </p>

                    </div>
                `;

                container.appendChild(
                    item
                );
            }
        );

        mettreAJourMemoireDroite(
            memories.length
        );

    } catch (error) {
        console.error(
            "Erreur mémoire :",
            error
        );

        container.innerHTML = `
            <div class="empty-state">

                <div>⚠️</div>

                <h3>
                    Impossible de charger la mémoire
                </h3>

            </div>
        `;
    }
}

function mettreAJourMemoireDroite(
    count
) {
    const preview =
        document.getElementById(
            "right-memory-preview"
        );

    if (!preview) return;

    preview.innerHTML = `
        <div class="mini-memory">

            <span>🧠</span>

            <div>

                <strong>
                    Mémoire active
                </strong>

                <small>
                    ${
                        count
                            ? `${count} souvenir${count > 1 ? "s" : ""} enregistré${count > 1 ? "s" : ""}`
                            : "Aucun souvenir"
                    }
                </small>

            </div>

        </div>
    `;
}

function demanderMemoire() {
    ouvrirVue("memory");

    chargerMemoire();
}

// ======================================================
// PROJETS
// ======================================================

async function chargerProjets() {
    const container =
        document.getElementById(
            "projects-container"
        );

    if (!container) return;

    try {
        const response =
            await fetch(
                "/projects"
            );

        if (
            response.status === 401
        ) {
            window.location.href =
                "/login";

            return;
        }

        const data =
            await response.json();

        const projects =
            data.projects ||
            [];

        container.innerHTML =
            "";

        if (
            projects.length === 0
        ) {
            container.innerHTML = `
                <div class="empty-state">

                    <div>📁</div>

                    <h3>
                        Aucun projet
                    </h3>

                    <p>
                        Crée ton premier projet
                        pour travailler avec Xyro.
                    </p>

                    <button
                        class="primary-btn"
                        onclick="ouvrirCreationProjet()"
                    >
                        ＋ Créer un projet
                    </button>

                </div>
            `;

            return;
        }

        projects.forEach(
            project => {
                const name =
                    project.name ||
                    "Projet";

                const context =
                    project.context ||
                    "Aucun contexte.";

                const card =
                    document.createElement(
                        "div"
                    );

                card.className =
                    "project-card";

                card.innerHTML = `
                    <div class="project-card-icon">
                        📁
                    </div>

                    <h3>
                        ${escapeHTML(name)}
                    </h3>

                    <p>
                        ${escapeHTML(context)}
                    </p>

                    <div class="project-card-footer">

                        <button
                            class="open-project-button"
                        >
                            Ouvrir
                        </button>

                        <button
                            class="danger"
                        >
                            Supprimer
                        </button>

                    </div>
                `;

                card.querySelector(
                    ".open-project-button"
                ).addEventListener(
                    "click",
                    () => {
                        selectionnerProjet(
                            name
                        );
                    }
                );

                card.querySelector(
                    ".danger"
                ).addEventListener(
                    "click",
                    () => {
                        supprimerProjet(
                            name
                        );
                    }
                );

                container.appendChild(
                    card
                );
            }
        );

    } catch (error) {
        console.error(
            "Erreur projets :",
            error
        );

        container.innerHTML = `
            <div class="empty-state">

                <div>⚠️</div>

                <h3>
                    Impossible de charger les projets
                </h3>

            </div>
        `;
    }
}

function ouvrirCreationProjet() {
    const modal =
        document.getElementById(
            "project-modal"
        );

    if (!modal) return;

    modal.classList.add(
        "open"
    );

    document.getElementById(
        "project-name"
    )?.focus();
}

async function creerProjet() {
    const nameInput =
        document.getElementById(
            "project-name"
        );

    const contextInput =
        document.getElementById(
            "project-context"
        );

    const name =
        nameInput?.value.trim();

    const context =
        contextInput?.value.trim() ||
        "";

    if (!name) {
        afficherNotification(
            "Donne un nom au projet."
        );

        nameInput?.focus();

        return;
    }

    try {
        const response =
            await fetch(
                "/projects",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        name,
                        context
                    })
                }
            );

        const data =
            await response
                .json()
                .catch(
                    () => ({})
                );

        if (!response.ok) {
            afficherNotification(
                data.error ||
                "Impossible de créer le projet."
            );

            return;
        }

        fermerModal(
            "project-modal"
        );

        if (nameInput) {
            nameInput.value =
                "";
        }

        if (contextInput) {
            contextInput.value =
                "";
        }

        chargerProjets();

        afficherNotification(
            "Projet créé avec succès."
        );

    } catch (error) {
        console.error(
            "Erreur création projet :",
            error
        );

        afficherNotification(
            "Erreur lors de la création du projet."
        );
    }
}

function selectionnerProjet(
    name
) {
    window.xyroProject =
        name;

    localStorage.setItem(
        PROJECT_KEY,
        name
    );

    ouvrirVue("chat");

    afficherNotification(
        `Projet "${name}" sélectionné.`
    );
}

async function supprimerProjet(
    name
) {
    if (
        !confirm(
            `Supprimer le projet "${name}" ?`
        )
    ) {
        return;
    }

    try {
        const response =
            await fetch(
                `/projects/${encodeURIComponent(name)}`,
                {
                    method: "DELETE"
                }
            );

        if (!response.ok) {
            afficherNotification(
                "Impossible de supprimer le projet."
            );

            return;
        }

        if (
            window.xyroProject ===
            name
        ) {
            window.xyroProject =
                "";

            localStorage.removeItem(
                PROJECT_KEY
            );
        }

        chargerProjets();

        afficherNotification(
            "Projet supprimé."
        );

    } catch (error) {
        console.error(
            "Erreur suppression projet :",
            error
        );
    }
}

// ======================================================
// OUTILS
// ======================================================

function preparerDevoirs() {
    ouvrirVue("chat");

    envoyer(
        "Aide-moi à faire mes devoirs. Explique-moi étape par étape et adapte tes explications à mon niveau."
    );
}

function afficherOutils() {
    ouvrirVue("tools");
}

// ======================================================
// INTERNET
// ======================================================

function demanderInternet() {
    ouvrirVue("internet");
}

function lancerRechercheInternet() {
    const webInput =
        document.getElementById(
            "internet-input"
        );

    const query =
        webInput?.value.trim();

    if (!query) {
        webInput?.focus();

        return;
    }

    ouvrirVue("chat");

    envoyer(
        `Utilise Internet pour répondre à cette demande : ${query}`
    );
}

function rechercheRapide(
    query
) {
    const webInput =
        document.getElementById(
            "internet-input"
        );

    if (webInput) {
        webInput.value =
            query;
    }

    lancerRechercheInternet();
}

// ======================================================
// VOIX
// ======================================================

let recognition = null;
let isListening = false;

function obtenirSpeechRecognition() {
    return (
        window.SpeechRecognition ||
        window.webkitSpeechRecognition ||
        null
    );
}

function demarrerDictation() {
    const Recognition =
        obtenirSpeechRecognition();

    if (!Recognition) {
        afficherNotification(
            "La reconnaissance vocale n'est pas disponible ici."
        );

        return;
    }

    if (isListening) {
        recognition?.stop();

        return;
    }

    recognition =
        new Recognition();

    recognition.lang =
        "fr-FR";

    recognition.continuous =
        false;

    recognition.interimResults =
        true;

    isListening = true;

    mettreAJourEtatVoix(
        true
    );

    recognition.onresult =
        event => {
            let transcript =
                "";

            for (
                let i =
                    event.resultIndex;
                i <
                    event.results.length;
                i++
            ) {
                transcript +=
                    event.results[i][0]
                        .transcript;
            }

            if (input) {
                input.value =
                    transcript;

                ajusterHauteurInput();
            }
        };

    recognition.onend =
        () => {
            isListening =
                false;

            mettreAJourEtatVoix(
                false
            );

            if (
                input?.value.trim()
            ) {
                envoyer();
            }
        };

    recognition.onerror =
        error => {
            console.error(
                "Erreur voix :",
                error
            );

            isListening =
                false;

            mettreAJourEtatVoix(
                false
            );
        };

    recognition.start();
}

function mettreAJourEtatVoix(
    listening
) {
    const orb =
        document.getElementById(
            "voice-orb"
        );

    const status =
        document.getElementById(
            "voice-status"
        );

    const description =
        document.getElementById(
            "voice-description"
        );

    const button =
        document.getElementById(
            "voice-button"
        );

    orb?.classList.toggle(
        "listening",
        listening
    );

    if (status) {
        status.textContent =
            listening
                ? "Je t'écoute..."
                : "Prêt à écouter";
    }

    if (description) {
        description.textContent =
            listening
                ? "Parle maintenant."
                : "Appuie sur le bouton pour commencer.";
    }

    if (button) {
        button.textContent =
            listening
                ? "⏹️ Arrêter"
                : "🎙️ Parler";
    }
}

function afficherVoix() {
    ouvrirVue("voice");
}

function lireTexte(text) {
    if (
        !settings.autoRead ||
        !("speechSynthesis" in window) ||
        !text
    ) {
        return;
    }

    window.speechSynthesis.cancel();

    const utterance =
        new SpeechSynthesisUtterance(
            text.slice(
                0,
                1800
            )
        );

    utterance.lang =
        "fr-FR";

    utterance.rate =
        0.98;

    utterance.pitch =
        1;

    window.speechSynthesis.speak(
        utterance
    );
}

function nettoyerTextePourVoix(
    text
) {
    return String(text)
        .replace(
            /```[\s\S]*?```/g,
            " bloc de code "
        )
        .replace(
            /[*_#>`]/g,
            ""
        )
        .replace(
            /\s+/g,
            " "
        )
        .trim();
}

// ======================================================
// PARAMÈTRES
// ======================================================

function chargerParametresUI() {
    const mode =
        document.getElementById(
            "setting-mode"
        );

    const personality =
        document.getElementById(
            "setting-personality"
        );

    const style =
        document.getElementById(
            "setting-style"
        );

    const autoRead =
        document.getElementById(
            "voice-auto-read"
        );

    if (mode) {
        mode.value =
            settings.mode;
    }

    if (personality) {
        personality.value =
            settings.personality;
    }

    if (style) {
        style.value =
            settings.response_style;
    }

    if (autoRead) {
        autoRead.checked =
            settings.autoRead;
    }

    mettreAJourModeUI();
}

function sauvegarderParametres() {
    const mode =
        document.getElementById(
            "setting-mode"
        );

    const personality =
        document.getElementById(
            "setting-personality"
        );

    const style =
        document.getElementById(
            "setting-style"
        );

    const autoRead =
        document.getElementById(
            "voice-auto-read"
        );

    if (mode) {
        settings.mode =
            mode.value;
    }

    if (personality) {
        settings.personality =
            personality.value;
    }

    if (style) {
        settings.response_style =
            style.value;
    }

    if (autoRead) {
        settings.autoRead =
            autoRead.checked;
    }

    localStorage.setItem(
        SETTINGS_KEY,
        JSON.stringify(
            settings
        )
    );

    mettreAJourModeUI();

    afficherNotification(
        "Paramètres enregistrés."
    );
}

function mettreAJourModeUI() {
    const label =
        document.getElementById(
            "current-mode-label"
        );

    if (!label) return;

    const names = {
        normal: "Normal",
        professeur: "Professeur",
        developpeur: "Développeur",
        gamer: "Gamer",
        creatif: "Créatif",
        xyro: "Xyro"
    };

    label.textContent =
        `Mode ${
            names[settings.mode] ||
            "Normal"
        }`;
}

// ======================================================
// QUITTER LES PARAMÈTRES
// ======================================================

function quitterParametres() {
    ouvrirVue("home");

    afficherNotification(
        "Retour à l'accueil."
    );
}

// ======================================================
// THÈME
// ======================================================

function appliquerTheme() {
    const theme =
        localStorage.getItem(
            THEME_KEY
        ) || "dark";

    document.body.classList.toggle(
        "light",
        theme === "light"
    );

    const button =
        document.getElementById(
            "theme-toggle"
        );

    if (button) {
        button.textContent =
            theme === "light"
                ? "☀"
                : "☾";
    }
}

function basculerTheme() {
    const current =
        localStorage.getItem(
            THEME_KEY
        ) || "dark";

    const next =
        current === "dark"
            ? "light"
            : "dark";

    localStorage.setItem(
        THEME_KEY,
        next
    );

    appliquerTheme();
}

// ======================================================
// NOTIFICATIONS
// ======================================================

function afficherNotifications() {
    afficherNotification(
        "🔔 Xyro.AI fonctionne normalement."
    );
}

// ======================================================
// RACCOURCIS
// ======================================================

document.addEventListener(
    "keydown",
    event => {
        if (
            event.ctrlKey &&
            event.key.toLowerCase() ===
                "k"
        ) {
            event.preventDefault();

            ouvrirVue("chat");

            input?.focus();
        }

        if (
            event.key ===
            "Escape"
        ) {
            document
                .querySelectorAll(
                    ".modal-overlay.open"
                )
                .forEach(
                    modal => {
                        modal.classList.remove(
                            "open"
                        );
                    }
                );
        }
    }
);

// ======================================================
// FERMER UNE MODALE EN CLIQUANT DEHORS
// ======================================================

document.addEventListener(
    "click",
    event => {
        if (
            event.target.classList.contains(
                "modal-overlay"
            )
        ) {
            event.target.classList.remove(
                "open"
            );
        }
    }
);

// ======================================================
// PROJET ACTIF
// ======================================================

window.xyroProject =
    localStorage.getItem(
        PROJECT_KEY
    ) || "";

// ======================================================
// INITIALISATION
// ======================================================

function initialiserXyro() {
    appliquerTheme();

    chargerParametresUI();

    chargerCompte();

    chargerHistorique();

    mettreAJourModeUI();

    console.log(
        "🚀 Xyro.AI V2.1 chargé."
    );
}

if (
    document.readyState ===
    "loading"
) {
    document.addEventListener(
        "DOMContentLoaded",
        initialiserXyro
    );
} else {
    initialiserXyro();
}


// =========================================================
// SIGNALEMENT DE COMPTE
// =========================================================
function ouvrirSignalement(){
    const modal = document.getElementById('report-modal');
    if(modal) modal.classList.add('open');
}

async function envoyerSignalement(){
    const target = document.getElementById('report-target')?.value.trim();
    const reason = document.getElementById('report-reason')?.value;
    const details = document.getElementById('report-details')?.value.trim() || '';
    if(!target){
        afficherNotification('Indique le pseudo ou l’ID du compte.');
        return;
    }
    try{
        const r = await fetch('/api/reports', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            credentials:'same-origin',
            body:JSON.stringify({reported_id:target, reason, details})
        });
        const data = await r.json().catch(()=>({}));
        if(!r.ok) throw new Error(data.error || 'Impossible d’envoyer le signalement.');
        fermerModal('report-modal');
        const t=document.getElementById('report-target');
        const d=document.getElementById('report-details');
        if(t)t.value=''; if(d)d.value='';
        afficherNotification('Signalement envoyé à l’administration.');
    }catch(e){
        afficherNotification('⚠️ '+e.message);
    }
}

window.ouvrirSignalement = ouvrirSignalement;
window.envoyerSignalement = envoyerSignalement;
