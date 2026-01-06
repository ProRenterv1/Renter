export {};

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: GoogleIdInitializeOptions) => void;
          renderButton: (parent: HTMLElement, options: GoogleIdButtonOptions) => void;
          cancel: () => void;
        };
      };
    };
  }

  interface GoogleIdInitializeOptions {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
    ux_mode?: "popup" | "redirect";
    login_uri?: string;
    auto_select?: boolean;
    prompt_parent_id?: string;
    use_fedcm_for_prompt?: boolean;
  }

  interface GoogleIdButtonOptions {
    type?: "standard" | "icon";
    theme?: "outline" | "filled_blue" | "filled_black";
    size?: "large" | "medium" | "small";
    text?: "signin_with" | "signup_with" | "continue_with" | "signin";
    shape?: "rectangular" | "pill" | "circle" | "square";
    logo_alignment?: "left" | "center";
    width?: string;
    locale?: string;
  }

  interface GoogleCredentialResponse {
    credential?: string;
    select_by?: string;
  }
}
