### Recording 2 — Configuration round trip

1. In **Open last folder**, click **OK**.
2. In **Choose annotation classes**, choose **Use annotation/default classes**.
3. In **Use model.conf?**, click **Yes**; wait until 9 images load.
4. Click the **Configuration** toolbar button.
5. On **Project**, replace **Author name** with `manual-tk-config`.
6. Scroll down and replace **Quality control methodology** with `manual-tk-qc`.
7. Open **Model** and click **Load model profile…**.
8. In **Select model profile**, select:

   `/private/tmp/teacup-gui-path-config-20260830-c/recorded_project/manual_profile.conf`

9. Open **Default class** and verify that `lithics`, `table`, and `figure_caption` are available. Select `table`.
10. Click **Browse** beside **Model weights**.
11. In **Select model weights**, select:

   `/private/tmp/teacup-gui-path-config-20260830-c/recorded_project/e2e_invalid_rfdetr.pt`

12. Open **Colours** and type `#123456` directly into **Snap/live-line colour**.
13. Click Configuration **Save**. If a warning appears, stop and report it.
14. Click Configuration **Close**.
15. Click the main-window **Save** button and wait for completion.
16. Close the main window using the macOS red button. No prompt is expected; if one appears, stop.

After closing, reply with `no deviations` or list every deviation.
