{
  "targets": [
    {
      "target_name": "doe_napi",
      "sources": ["native/doe_napi.c"],
      "include_dirs": [],
      "conditions": [
        ["OS=='mac'", {
          "xcode_settings": {
            "OTHER_CFLAGS": ["-std=c11"],
            "MACOSX_DEPLOYMENT_TARGET": "13.0"
          }
        }],
        ["OS=='linux'", {
          "cflags": ["-std=c11"]
        }]
      ]
    }
  ]
}
