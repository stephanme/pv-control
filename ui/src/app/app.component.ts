import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, FormControl } from '@angular/forms';
import { MatSlideToggleChange } from '@angular/material/slide-toggle';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { HttpStatusService } from './http-status.service';

import { PvControl, PvControlService } from './pv-control.service';

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
    charger: {
      phases: 3,
      max_current: 0,
      power_car: 0
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
    this.pvControlService.getPvControl().subscribe(cc => {
      // console.log(`Refresh: phases = ${cc.phases}`);
      this.pvControl = cc;
      this.onePhaseSelectorControl.setValue(cc.charger.phases === 1);
    },
      () => { }
    );
  }

  onPhaseChange(event: MatSlideToggleChange): void {
    const phases = event.checked ? 1 : 3;
    // console.log(`onPhaseChange = ${phases}`);
    this.pvControlService.putPvControlPhases(phases).subscribe(
      () => this.refresh(),
      () => { }
    );
  }
}
