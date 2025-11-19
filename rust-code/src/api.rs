use std::collections::HashSet;

use serde::{Deserialize, Serialize};

use crate::qu;

#[derive(Deserialize, Serialize, Clone)]
pub struct Blacklist {
    pub blacklist: HashSet<String>,
}

#[derive(Deserialize)]
pub struct QueryRequest {
    pub query: String,
    pub limit: Option<u64>,
    pub parent: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct QueryResponse {
    pub items: Vec<qu::Item>,
}

// the following are inherited from the DG VA / STS API

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FunctionCallRequestItem {
    pub id: String,
    pub name: String,
    pub arguments: String,
    pub client_side: bool,
}

#[allow(clippy::large_enum_variant)]
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(tag = "type")]
#[serde(deny_unknown_fields)]
pub enum ServerMessage {
    Welcome {
        session_id: String,
    },

    UserStartedSpeaking,

    FunctionCallRequest {
        functions: Vec<FunctionCallRequestItem>,
    },
}

#[allow(clippy::large_enum_variant)]
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(tag = "type")]
#[serde(deny_unknown_fields)]
pub enum ClientMessage {
    Settings(Settings),
}

#[derive(Deserialize, Serialize, Debug, Default, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    #[serde(default)]
    pub audio: Audio,
    pub agent: Agent,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct Audio {
    pub input: AudioInput,
    pub output: AudioOutput,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct AudioInput {
    pub encoding: String,
    pub sample_rate: usize,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct AudioOutput {
    pub encoding: String,
    pub sample_rate: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bitrate: Option<usize>,
    #[serde(skip_serializing_if = "should_skip_container")]
    #[serde(default = "default_container")]
    pub container: String,
}

fn should_skip_container(container: &String) -> bool {
    let skip = container == "none";
    skip
}

fn default_container() -> String {
    "none".to_string()
}

impl Default for Audio {
    fn default() -> Self {
        Self {
            input: AudioInput {
                encoding: "linear16".to_string(),
                sample_rate: 16000,
            },
            output: AudioOutput {
                encoding: "linear16".to_string(),
                sample_rate: 16000,
                bitrate: None,
                container: "none".to_string(),
            },
        }
    }
}

#[derive(Deserialize, Serialize, Debug, Default, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct Context {
    pub messages: Vec<TttMessage>,
    pub replay: bool,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(tag = "type")]
pub enum TttMessage {
    History(HistoryMessage),
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(untagged)]
pub enum HistoryMessage {
    UserMessage {
        role: String,
        content: String,
    },
    AssistantMessage {
        role: String,
        content: String,
    },
    FunctionCallMessage {
        function_calls: Vec<FunctionCall>,
    },
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
pub struct FunctionCall {
    pub id: String,
    pub name: String,
    pub client_side: bool,
    pub arguments: String,
    pub response: String,
}


#[derive(Deserialize, Serialize, Debug, Default, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct Agent {
    #[serde(default = "default_language")]
    pub language: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context: Option<Context>,
    pub listen: Listen,
    pub think: Think,
    pub speak: Speak,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub greeting: Option<String>,
}

fn default_language() -> String {
    "en".to_string()
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct Listen {
    pub provider: ListenProvider,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct ListenProvider {
    #[serde(rename = "type")]
    pub provider_type: String,
    pub model: String,
    #[serde(default)]
    pub keyterms: Vec<String>,
    #[serde(default)]
    pub smart_format: bool,
}

impl Default for Listen {
    fn default() -> Listen {
        Self {
            provider: ListenProvider {
                provider_type: "deepgram".to_string(),
                model: "nova-2".to_string(),
                keyterms: Vec::new(),
                smart_format: false,
            },
        }
    }
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct Speak {
    pub provider: SpeakProvider,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub endpoint: Option<Endpoint>,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct SpeakProvider {
    #[serde(rename = "type")]
    pub provider_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub voice: Option<VoiceConfig>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub language: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub language_code: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub engine: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub credentials: Option<AwsCredentials>,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(untagged)]
pub enum VoiceConfig {
    String(String),
    Object { mode: String, id: String },
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct AwsCredentials {
    #[serde(rename = "type")]
    pub credential_type: String, // "IAM" or "STS"
    pub region: String,
    pub access_key_id: String,
    pub secret_access_key: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_token: Option<String>,
}

impl Default for Speak {
    fn default() -> Self {
        Self {
            provider: SpeakProvider {
                provider_type: "deepgram".to_string(),
                model: Some("aura-asteria-en".to_string()),
                model_id: None,
                voice: None,
                language: None,
                language_code: None,
                engine: None,
                credentials: None,
            },
            endpoint: None,
        }
    }
}

#[derive(Deserialize, Clone, Debug, PartialEq, Hash, Eq)]
#[serde(rename_all = "snake_case")]
#[serde(deny_unknown_fields)]
pub enum TtsProvider {
    Deepgram,
    ElevenLabs,
    Cartesia,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct Think {
    pub provider: ThinkProvider,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub endpoint: Option<Endpoint>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prompt: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context_length: Option<ContextLength>,
    #[serde(default)]
    pub functions: Vec<Function>,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct ThinkProvider {
    #[serde(rename = "type")]
    pub provider_type: String,
    pub model: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub temperature: Option<f32>,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(deny_unknown_fields)]
pub struct Endpoint {
    pub url: String,
    pub headers: std::collections::HashMap<String, String>,
}

#[derive(Deserialize, Serialize, Debug, PartialEq, Clone)]
#[serde(untagged)]
pub enum ContextLength {
    Number(u32),
    Max(String), // "max"
}

impl Default for Think {
    fn default() -> Self {
        Self {
            provider: ThinkProvider {
                provider_type: "open_ai".to_string(),
                model: "gpt-4o-mini".to_string(),
                temperature: None,
            },
            endpoint: None,
            prompt: None,
            context_length: None,
            functions: Vec::new(),
        }
    }
}

#[derive(Deserialize, Serialize, Clone, Debug, PartialEq, Hash, Eq)]
#[serde(rename_all = "snake_case")]
#[serde(tag = "type")]
#[serde(deny_unknown_fields)]
pub enum Provider {
    Anthropic,
    OpenAi,
    XAi,
    Groq,
}

#[derive(Debug, Serialize, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Function {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub endpoint: Option<Endpoint>,
}
