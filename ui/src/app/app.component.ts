import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, FormControl } from '@angular/forms';
import { MatSlideToggleChange } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { HttpStatusService } from './http-status.service';

import { ChargeMode, PvControl, PvControlService } from './pv-control.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit, OnDestroy {
  private unsubscribe: Subject<void> = new Subject();

  busy$ = this.httpStatusService.busy();
  pvControl: PvControl = {
    meter: {
      power_pv: 0,
      power_consumption: 0,
      power_grid: 0,
    },
    wallbox: {
      allow_charging: false,
      max_current: 0,
      phases_in: 3,
      phases_out: 0,
      power: 0,
    },
    controller: {
      mode: ChargeMode.OFF_3P,
      desired_mode: ChargeMode.OFF_3P
    }
  };
  onePhaseSelectorControl = this.fb.control([false]);

  constructor(
    private fb: FormBuilder, private snackBar: MatSnackBar,
    private httpStatusService: HttpStatusService, private pvControlService: PvControlService) { }

  ngOnInit(): void {
    this.httpStatusService.httpError().pipe(takeUntil(this.unsubscribe)).subscribe(errmsg => {
      console.log(`httpError: ${errmsg}`);
      this.snackBar.open(errmsg, 'Dismiss', {
        duration: 10000
      });
    });
    this.refresh();
  }

  ngOnDestroy(): void {
    this.unsubscribe.next();
    this.unsubscribe.complete();
  }

  refresh(): void {
    this.pvControlService.getPvControl().subscribe(pv => {
      this.pvControl = pv;
      this.onePhaseSelectorControl.setValue(pv.controller.desired_mode === ChargeMode.OFF_1P); // TODO
    },
      () => { }
    );
  }

  onPhaseChange(event: MatSlideToggleChange): void {
    const desiredMode = event.checked ? ChargeMode.OFF_1P : ChargeMode.OFF_3P;
    this.pvControlService.putPvControlDesiredChargeMode(desiredMode).subscribe(
      () => this.refresh(),
      () => { }
    );
  }
}
