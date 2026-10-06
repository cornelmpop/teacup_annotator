### Recording 7 — Model configuration failure

1. In **Open last folder**, click **OK**.
2. In **Choose annotation classes**, choose **Use annotation/default classes**.
3. In **Use model.conf?**, click **Yes**; wait until 9 images load.
4. Click the **Run model** toolbar button.
5. In **Replace model annotations?**, click **Yes**.
6. In **Select RF-DETR weights**, select:

   `/private/tmp/teacup-gui-path-model-failure-20260830-a/recorded_project/e2e_invalid_rfdetr.pt`

7. Wait for the **Could not configure model** error-details window.
8. Confirm that the window contains a traceback, then click its **Close** button.
9. Click **Save** and wait for completion.
10. Close the main window using the macOS red button. No prompt is expected; if one appears, stop.

After closing, reply with `no deviations` or list every deviation.
